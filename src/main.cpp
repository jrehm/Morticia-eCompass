/** @file main.cpp
 *  @brief Morticia eCompass - 9DOF Heading/Attitude Sensor for Signal K
 *
 *  Hardware: SH-ESP32 + BRKT-STBC-AGM01 (FXOS8700CQ + FXAS21002C)
 *  Outputs:  Compass Heading, Magnetic Heading (with deviation table),
 *            Attitude (yaw/pitch/roll), Rate of Turn,
 *            Magnetic Calibration diagnostics
 *
 *  Based on SignalK-Orientation example by Bjarne Hansen
 *  Customized for SeaCart 30 trimaran "Morticia" by Jeff Rehm
 *
 *  I2C addresses and pin definitions are set via build_flags
 *  in platformio.ini so this code is hardware-portable.
 */

#include <memory>

// Connectivity watchdog
#include "esp_task_wdt.h"

// SensESP v3 headers
#include "sensesp.h"
#include "sensesp/sensors/sensor.h"
#include "sensesp/signalk/signalk_output.h"
#include "sensesp/system/lambda_consumer.h"
#include "sensesp_app_builder.h"

// For magnetic calibration save button
#include "sensesp/sensors/digital_input.h"
#include "sensesp/transforms/debounce.h"

// For heading correction transforms
#include "sensesp/transforms/angle_correction.h"
#include "sensesp/transforms/curveinterpolator.h"

// For Attitude (combined roll, pitch, yaw) output
#include "sensesp/signalk/signalk_types.h"

// For thermal drift compensation (combines heading + temperature, see
// docs/thermal-drift-compensation-handoff.md)
#include "sensesp/transforms/zip.h"
#include "sensesp/transforms/lambda_transform.h"
#include <tuple>

// Custom API endpoints — registered on SensESP's primary HTTP server (port 80)
// via a local patch that adds get_http_server() to SensESPApp (see DECISIONS.md).
#include "sensesp/net/http_server.h"
#include <ArduinoJson.h>
#include <Preferences.h>

// Orientation sensor library
#include "orientation_sensor.h"
#include "signalk_orientation.h"

// Power monitoring (INA226 / INA228)
// To transition from INA226 to INA228 at the battery position:
//   1. Uncomment #define USE_INA228 below
//   2. Reflash — no wiring changes needed (same address, same shunt)
#define USE_INA228
#include "INA226.h"
#ifdef USE_INA228
#include "INA228.h"
#endif

// ---- Hardware Configuration ----
// Set via platformio.ini build_flags, with fallback defaults here.
// BRKT-STBC-AGM01: 0x1E (accel/mag), 0x20 (gyro)
// SH-ESP32 I2C header: GPIO16 (SDA), GPIO17 (SCL)
#ifndef BOARD_ACCEL_MAG_I2C_ADDR
#define BOARD_ACCEL_MAG_I2C_ADDR (0x1E)
#endif
#ifndef BOARD_GYRO_I2C_ADDR
#define BOARD_GYRO_I2C_ADDR (0x20)
#endif
#ifndef PIN_I2C_SDA
#define PIN_I2C_SDA (16)
#endif
#ifndef PIN_I2C_SCL
#define PIN_I2C_SCL (17)
#endif

// Optional: physical button to save magnetic calibration
#define PIN_SWITCH_CAL_SAVE (0)
#define SWITCH_ACTIVE_STATE (0)

// Output rates
#define ORIENTATION_REPORTING_INTERVAL_MS (100)
#define ATTITUDE_REPORTING_INTERVAL_MS    (200)
#define CALIBRATION_REPORTING_INTERVAL_MS (4000)
#define RATE_REPORTING_INTERVAL_MS        (200)
#define POWER_REPORTING_INTERVAL_MS       (1000)
// Faster than CALIBRATION_REPORTING_INTERVAL_MS: DC drift and magnoise
// direction analysis both average this vector over a window at the client
// end, so the raw feed needs to be finer-grained than the 4 s calibration
// diagnostics. See TODO.md "eCompass DC Hard-Iron Drift" and
// handoffs/magnoise-instrumentation.md.
#define MAG_VECTOR_REPORTING_INTERVAL_MS  (1000)
// Dedicated, faster temperature feed for the thermal-compensation Zip only
// (see COMPASS HEADING section below) -- decoupled from
// CALIBRATION_REPORTING_INTERVAL_MS so headingCompass/headingMagnetic aren't
// throttled down to the (deliberately slow) magfit/magsolver diagnostic
// rate. 200ms = 5Hz, comfortably above the requested 2Hz floor.
#define THERMAL_ZIP_INTERVAL_MS           (200)

// Power monitoring I2C addresses
// Solar: INA226 at default address (A0, A1 floating)
#define INA_SOLAR_I2C_ADDR   (0x40)
// Battery: INA228 (target) or INA226 (interim) — A0 pin tied to VS on the board to set 0x41
#define INA_BATTERY_I2C_ADDR (0x41)

// Shunt resistor configuration
// Formula: shunt_ohms = mV_rating / (A_rating * 1000)
//   50A/75mV → 0.00150, 20A/75mV → 0.00375, 20A/50mV → 0.00250
#define INA_SOLAR_SHUNT_OHMS   (0.00375f)  // 20A/75mV external shunt
#define INA_BATTERY_SHUNT_OHMS (0.00375f)  // 20A/75mV external shunt
// Max expected current for LSB calibration (sets resolution — use realistic peak, not shunt max)
// API: setMaxCurrentShunt(INA_MAX_AMPS, INA_x_SHUNT_OHMS)
#define INA_MAX_AMPS           (10.0f)

// Battery pack specifications — used for remaining capacity and SoC calculations.
// Update if the battery is replaced with a different pack.
// Eco-Worthy 12.8V 100Ah LiFePO4 (4S, nominal 12.8V)
#define INA_BATTERY_NOMINAL_AH   (100.0f)   // nameplate capacity
#define INA_BATTERY_NOMINAL_V    (12.8f)    // nominal voltage for Wh calculation
#define INA_BATTERY_NOMINAL_WH   (INA_BATTERY_NOMINAL_AH * INA_BATTERY_NOMINAL_V)
// Sign convention: discharge is NEGATIVE accumulator direction.
// If remaining values increase during discharge, swap shunt sense wires (IN+/IN-)
// or negate the getCharge()/getEnergy() calls below.

// Battery SoC persistence — see docs/battery-soc-persistence-handoff.md for
// the full rationale and tradeoffs behind these values.
//
// Periodic NVS checkpoint: bounds SoC staleness after an unplanned power
// loss. Does not correct drift — see full-charge detector below for that.
#define CHECKPOINT_INTERVAL_MS           (30 * 60 * 1000)  // 30 min

// Automated full-charge detection: when voltage/current sit within these
// bounds for most of a rolling window, auto-seed SoC to 100%. Thresholds are
// deliberately not tightened beyond the original naive guess — dwell-time
// filtering (not threshold precision) is what rejects passing-cloud false
// positives; see the handoff doc's InfluxDB analysis.
#define FULL_CHARGE_VOLTAGE_THRESHOLD_V  (14.4f)   // 4S LiFePO4: ~95%+ SoC at near-zero current
#define FULL_CHARGE_CURRENT_THRESHOLD_A  (0.2f)    // "tapering"
#define FULL_CHARGE_RESET_VOLTAGE_V      (14.0f)   // hysteresis: below this, a new discharge cycle has begun
#define FULL_CHARGE_SAMPLE_INTERVAL_MS   (10 * 1000)      // 10 s sampling cadence
#define FULL_CHARGE_WINDOW_MINUTES       (20)
#define FULL_CHARGE_WINDOW_SAMPLES \
    (FULL_CHARGE_WINDOW_MINUTES * 60 * 1000 / FULL_CHARGE_SAMPLE_INTERVAL_MS)  // 120
#define FULL_CHARGE_PASS_RATIO           (0.80f)

// Connectivity watchdog: reboot ESP32 if Signal K connection
// is lost for this many milliseconds. Handles edge cases where
// the SKWSClient retry loop gets stuck in a non-disconnected
// state (e.g., after Signal K server restart).
#define SK_CONNECTION_TIMEOUT_MS (60 * 1000)  // 60 seconds

// Hardware watchdog: reboot if main loop stalls completely.
// This catches hard lockups (I2C bus hang, stack overflow, etc.)
#define HW_WATCHDOG_TIMEOUT_S (120)  // 2 minutes

using namespace sensesp;

// NVS-backed battery config — updated via POST /api/battery/configure.
// Compile-time #defines are used as fallback defaults on first boot.
static float g_battery_capacity_ah = INA_BATTERY_NOMINAL_AH;
static float g_battery_nominal_v   = INA_BATTERY_NOMINAL_V;
static float g_battery_seed_ah     = INA_BATTERY_NOMINAL_AH;  // Ah remaining at last configure

// NVS-backed thermal compensation coefficients — updated via POST
// /api/thermal/config. Compile-time defaults are the fit from the
// 2026-07-30/8-01 new-location analysis (analysis/thermal-drift/
// newloc_correlation_summary.md in Morticia-eCompass, -0.17 deg/C, T_ref
// 30.4 C; deployed live via the API on 2026-08-01), which superseded the
// original 2026-07-13 dockside fit (-1.021 deg/C, T_ref 30.07 C) once the
// sensor was relocated ~3ft from the SensESP PCB (ADR-013 in
// morticia-project). See docs/thermal-drift-compensation-handoff.md.
static constexpr float kThermalSlopeRadPerKDefault = -0.0029671f;
static constexpr float kThermalRefTempKDefault = 303.55f;
static float g_thermal_slope_rad_per_k = kThermalSlopeRadPerKDefault;
static float g_thermal_ref_temp_k = kThermalRefTempKDefault;

// Full-charge detector state — file scope (not a local static in setup())
// so /api/battery/config can report live detector status. See
// docs/battery-soc-persistence-handoff.md for the dwell-time design.
static bool full_charge_samples[FULL_CHARGE_WINDOW_SAMPLES] = {};
static size_t full_charge_sample_idx = 0;
static size_t full_charge_samples_filled = 0;
static uint16_t full_charge_pass_count = 0;
static bool full_charge_latched = false;

static float GetFullChargePassRatio() {
  return full_charge_samples_filled > 0
      ? static_cast<float>(full_charge_pass_count) / full_charge_samples_filled
      : 0.0f;
}

// Magnetic-calibration change-detector state — file scope so both the
// onRepeat() detector and its SignalK RepeatSensor outputs can share it.
// The fusion library (OrientationSensorFusion-ESP, fusion/magnetic.c)
// re-solves the magnetic calibration from a rolling sample buffer every
// CAL_INTERVAL_SECS (5 min) and auto-adopts the result if its fit error
// looks better than the current one -- and the current one's fit error is
// deliberately "aged" upward (~1%/24h) so a stale calibration eventually
// loses to a fresh one even without any real change. At a mooring, hours on
// one heading means that rolling buffer is a narrow cluster of near-
// identical orientations, which can produce a numerically better fit that
// isn't actually more correct -- shifting the reported heading by double
// digits of degrees with no signal beyond the raw magfit telemetry. These
// hold the size of the most recent such event until the next one occurs.
static float g_magcal_event_fitdelta_pct = 0.0f;
static float g_magcal_event_headingdelta_deg = 0.0f;

// Deviation Table - enter via web UI or hard-code after compass swing
class DeviationInterpolator : public CurveInterpolator {
 public:
  DeviationInterpolator(String config_path = "")
      : CurveInterpolator(NULL, config_path) {
    // Default: 1:1 passthrough (no deviation correction).
    // After a compass swing, replace with actual deviation values
    // via the SensESP web UI, or hard-code here.
    clear_samples();
    add_sample(CurveInterpolator::Sample(0.0, 0.0));
    add_sample(CurveInterpolator::Sample(3.14159, 3.14159));
    add_sample(CurveInterpolator::Sample(6.28318, 6.28318));
  }
};

void setup() {
  pinMode(0, OUTPUT);
  pinMode(2, OUTPUT);
  pinMode(4, OUTPUT);
  SetupLogging(ESP_LOG_INFO);
  ESP_LOGI(TAG, "Morticia eCompass v%s starting", FIRMWARE_VERSION);

  // Load NVS-backed battery config (falls back to compile-time defaults if not yet set)
  {
    Preferences prefs;
    prefs.begin("battery", true);
    g_battery_capacity_ah = prefs.getFloat("capacity_ah", INA_BATTERY_NOMINAL_AH);
    g_battery_nominal_v   = prefs.getFloat("nominal_v",   INA_BATTERY_NOMINAL_V);
    g_battery_seed_ah     = prefs.getFloat("seed_ah",     INA_BATTERY_NOMINAL_AH);
    prefs.end();
  }
  ESP_LOGI(TAG, "Battery config: %.1f Ah cap, %.1f Ah seed, %.1f V nominal",
           g_battery_capacity_ah, g_battery_seed_ah, g_battery_nominal_v);

  // Load NVS-backed thermal compensation coefficients (falls back to
  // compile-time defaults if not yet set) — see
  // docs/thermal-drift-compensation-handoff.md
  {
    Preferences prefs;
    prefs.begin("thermalcomp", true);
    g_thermal_slope_rad_per_k = prefs.getFloat("slope", kThermalSlopeRadPerKDefault);
    g_thermal_ref_temp_k      = prefs.getFloat("tref_k", kThermalRefTempKDefault);
    prefs.end();
  }
  ESP_LOGI(TAG, "Thermal compensation: slope %.6f rad/K, T_ref %.2f K",
           g_thermal_slope_rad_per_k, g_thermal_ref_temp_k);

  // Build SensESP Application
  SensESPAppBuilder builder;
  sensesp_app = (&builder)
      ->set_hostname("SensESP")
      //->set_sk_server("halos.local", 3000)  // set via WebUI
      //->set_wifi_client("YourSSID", "YourPassword")
      ->enable_uptime_sensor()
      ->enable_ip_address_sensor()
      ->enable_free_mem_sensor()
      ->enable_system_hz_sensor()
      ->enable_ota("morticia")
      ->get_app();

  // Note: set_client_id() was a local SensESP patch removed in 3.3.1+.
  // SK source key is now derived from the hostname set in SensESPAppBuilder.

  // ========== WATCHDOG SETUP ==========
  // Hardware watchdog: reboots if the main event loop stalls
  // (I2C bus hang, stack overflow, infinite loop, etc.)
  esp_task_wdt_config_t wdt_config = {
      .timeout_ms = HW_WATCHDOG_TIMEOUT_S * 1000,
      .idle_core_mask = 0,  // don't watch idle tasks
      .trigger_panic = true  // reboot on timeout
  };
  esp_task_wdt_reconfigure(&wdt_config);
  esp_task_wdt_add(NULL);  // monitor the main (loopTask) task
  ESP_LOGI("eCompass", "Hardware watchdog enabled (%ds timeout)",
           HW_WATCHDOG_TIMEOUT_S);

  // Connectivity watchdog: reboots if Signal K connection is lost
  // for longer than SK_CONNECTION_TIMEOUT_MS. This catches the edge
  // case where SKWSClient's retry loop gets stuck in Authorizing or
  // Connecting state after a Signal K server restart.
  static unsigned long last_sk_connected_ms = millis();

  event_loop()->onRepeat(15000, []() {
    // Feed the hardware watchdog — proves the event loop is alive
    esp_task_wdt_reset();

    // Check Signal K connection health
    auto ws_client = sensesp_app->get_ws_client();
    if (ws_client && ws_client->is_connected()) {
      last_sk_connected_ms = millis();
    } else {
      unsigned long disconnected_ms = millis() - last_sk_connected_ms;
      if (disconnected_ms > SK_CONNECTION_TIMEOUT_MS) {
        ESP_LOGW("eCompass",
                 "Signal K disconnected for %lu s — rebooting",
                 disconnected_ms / 1000);
        delay(100);  // let the log message flush
        ESP.restart();
      } else if (disconnected_ms > 30000) {
        // Log periodic status while disconnected
        ESP_LOGI("eCompass",
                 "Signal K disconnected for %lu s (reboot at %d s)",
                 disconnected_ms / 1000,
                 SK_CONNECTION_TIMEOUT_MS / 1000);
      }
    }
  });

  // Signal K Paths
  const char* kSKPathHeadingCompass  = "navigation.headingCompass";
  const char* kSKPathHeadingMagnetic = "navigation.headingMagnetic";
  const char* kSKPathAttitude        = "navigation.attitude";
  const char* kSKPathTurnRate        = "navigation.rateOfTurn";
  const char* kSKPathMagFit          = "orientation.calibration.magfit";
  const char* kSKPathMagFitTrial     = "orientation.calibration.magfittrial";
  const char* kSKPathMagSolver       = "orientation.calibration.magsolver";
  const char* kSKPathMagNoise        = "orientation.calibration.magnoise";
  const char* kSKPathMagFieldMag      = "orientation.calibration.magfieldmagnitude";
  const char* kSKPathMagFieldMagTrial = "orientation.calibration.magfieldmagnitudetrial";
  const char* kSKPathMagInclination   = "orientation.calibration.maginclination";
  const char* kSKPathMagFieldVectorX = "orientation.calibration.magfieldvector.x";
  const char* kSKPathMagFieldVectorY = "orientation.calibration.magfieldvector.y";
  const char* kSKPathMagFieldVectorZ = "orientation.calibration.magfieldvector.z";
  const char* kSKPathMagCalEventFit      = "orientation.calibration.lastcaleventfitdeltapct";
  const char* kSKPathMagCalEventHeading  = "orientation.calibration.lastcaleventheadingdeltadeg";
  const char* kSKPathTemperature     = "environment.inside.ecompass.temperature";
  const char* kConfigPathNone = "";

  // ---- Initialize Orientation Sensor ----
  // SignalK-Orientation v1.0.1 changed constructor to 6 args (added separate
  // mag_i2c_addr and therm_i2c_addr for STM sensor support). For FXOS8700CQ,
  // accel, mag, and therm are all on the same IC at the same address.
  auto* orientation_sensor = new OrientationSensor(
      PIN_I2C_SDA, PIN_I2C_SCL,
      BOARD_ACCEL_MAG_I2C_ADDR,   // accel (FXOS8700CQ)
      BOARD_ACCEL_MAG_I2C_ADDR,   // mag   (FXOS8700CQ — same chip)
      BOARD_GYRO_I2C_ADDR,        // gyro  (FXAS21002C)
      BOARD_ACCEL_MAG_I2C_ADDR);  // therm (FXOS8700CQ — same chip)
  const int fusionIntervalMs = 1000 / orientation_sensor->GetFusionRateHz();
  event_loop()->onRepeat(fusionIntervalMs,
      [orientation_sensor]() { orientation_sensor->ReadAndProcessSensors(); });

  // ========== TEMPERATURE (FXOS8700CQ onboard thermometer) ==========
  // Created before COMPASS HEADING (moved up from its original position
  // later in setup()) because the thermal compensation transform below
  // needs both `compass_heading` and `temperature` producers to exist
  // before it can zip them together. See
  // docs/thermal-drift-compensation-handoff.md.
  auto* sensor_temperature = new OrientationValues(
      orientation_sensor, OrientationValues::kTemperature);
  auto temperature = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_temperature]() { return sensor_temperature->ReportValue(); });
  auto temperature_metadata = std::make_shared<SKMetadata>();
  temperature_metadata->units_ = "K";
  temperature_metadata->description_ = "Temperature reported by orientation sensor IC";
  temperature_metadata->display_name_ = "eCompass Temperature";
  temperature_metadata->short_name_ = "Comp. T";
  auto temperature_output = std::make_shared<SKOutput<float>>(
      kSKPathTemperature, kConfigPathNone, temperature_metadata);
  temperature->connect_to(temperature_output);

  // Separate, faster-reporting temperature feed used ONLY to drive the
  // thermal-compensation Zip below (see COMPASS HEADING). Temperature has
  // a minutes-long thermal time constant, so polling it 20x more often
  // costs nothing physically -- but it lets the corrected heading emit at
  // THERMAL_ZIP_INTERVAL_MS instead of being capped at the much slower
  // CALIBRATION_REPORTING_INTERVAL_MS used for magfit/magsolver
  // diagnostics. `environment.inside.ecompass.temperature` above is
  // unaffected and keeps reporting at its original (slower) rate.
  auto temperature_fast = std::make_shared<RepeatSensor<float>>(
      THERMAL_ZIP_INTERVAL_MS,
      [sensor_temperature]() { return sensor_temperature->ReportValue(); });

  // ========== COMPASS HEADING ==========
  auto* sensor_heading = new OrientationValues(
      orientation_sensor, OrientationValues::kCompassHeading);
  auto compass_heading = std::make_shared<RepeatSensor<float>>(
      ORIENTATION_REPORTING_INTERVAL_MS,
      [sensor_heading]() { return sensor_heading->ReportValue(); });

  // Thermal drift compensation — see docs/thermal-drift-compensation-handoff.md
  // for the derivation. Combines the raw heading and temperature producers
  // into a tuple (Zip), then applies a linear correction fitted against
  // 5 days of dockside data (-1.021 deg/C, no lag, no hysteresis, so a
  // simple linear fit is sufficient — no lookup table needed).
  // max_age=1000ms: temperature_fast reports every THERMAL_ZIP_INTERVAL_MS
  // (200ms), so 1s gives ~5x margin without masking a real sensor stall.
  // Zip only emits once BOTH inputs have produced a fresh value since the
  // last emission, so the output rate is capped by the slower of the two —
  // previously that was `temperature` at CALIBRATION_REPORTING_INTERVAL_MS
  // (4000ms/0.25Hz), throttling headingCompass/headingMagnetic down to
  // 0.25Hz even though heading itself is ready at 10Hz. Using
  // `temperature_fast` here instead raises that ceiling to
  // THERMAL_ZIP_INTERVAL_MS (200ms/5Hz).
  auto* thermal_zip = new Zip<float, float>(1000);
  compass_heading->connect_to(std::get<0>(thermal_zip->consumers));
  temperature_fast->connect_to(std::get<1>(thermal_zip->consumers));

  auto thermal_compensation = std::make_shared<
      LambdaTransform<std::tuple<float, float>, float>>(
      [](std::tuple<float, float> input) -> float {
        float heading_rad = std::get<0>(input);
        float temp_k = std::get<1>(input);
        // Subtract, not add: heading residual = slope*(T-Tref) (slope is
        // negative), so to cancel it out we need -slope*(T-Tref). Verified
        // numerically against analysis/thermal-drift/validate.py's
        // apply_correction() -- the "+" form was tried first and confirmed
        // (by rerunning it against the cleaned dataset) to double the drift
        // instead of removing it.
        return heading_rad -
               g_thermal_slope_rad_per_k * (temp_k - g_thermal_ref_temp_k);
      });
  thermal_zip->connect_to(thermal_compensation);

  auto compass_sk_output = std::make_shared<SKOutput<float>>(
      kSKPathHeadingCompass, kConfigPathNone);

  const char* kConfigPathHeadingOffset = "/sensors/hdg/offset";
  auto* mountingOffset = new AngleCorrection((PI / 2.0), 0.0, kConfigPathHeadingOffset);
  ConfigItem(mountingOffset)
      ->set_title("Mounting Offset")
      ->set_description("Adjustment for sensor mounting orientation (radians)")
      ->set_sort_order(400);

  const char* kConfigPathDeviation = "/sensors/hdg/deviation";
  auto* deviationInterpolator = new DeviationInterpolator(kConfigPathDeviation);
  ConfigItem(deviationInterpolator)
      ->set_title("Deviation Table")
      ->set_description("Compass deviation correction (JSON: [{input:rad,output:rad},...])")
      ->set_sort_order(1001);

  auto magneticheading_sk_output = std::make_shared<SKOutput<float>>(
      kSKPathHeadingMagnetic, kConfigPathNone);

  thermal_compensation
      ->connect_to(mountingOffset)
      ->connect_to(compass_sk_output)
      ->connect_to(deviationInterpolator)
      ->connect_to(new AngleCorrection(0.0, 0.0, kConfigPathNone))
      ->connect_to(magneticheading_sk_output);

  // HTTP endpoint: return current thermal compensation coefficients
  // (human units: deg/C, C). See docs/thermal-drift-compensation-handoff.md.
  // Usage: GET http://sensesp.local/api/thermal/config
  auto thermal_config_get_handler = std::make_shared<HTTPRequestHandler>(
      1 << HTTP_GET, "/api/thermal/config",
      [](httpd_req_t* req) {
        char resp[160];
        snprintf(resp, sizeof(resp),
                 "{\"slope_deg_per_c\":%.4f,\"tref_c\":%.3f}",
                 g_thermal_slope_rad_per_k * (180.0f / PI),
                 g_thermal_ref_temp_k - 273.15f);
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, resp, strlen(resp));
        return ESP_OK;
      });
  sensesp_app->get_http_server()->add_handler(thermal_config_get_handler);

  // HTTP endpoint: update thermal compensation coefficients (e.g. after a
  // future re-run of analysis/thermal-drift/) without a reflash.
  // Body (both fields optional — omitting keeps the current NVS value):
  //   {"slope_deg_per_c": -1.021, "tref_c": 30.07}
  // Updates NVS, returns JSON confirmation.
  // Usage: POST http://sensesp.local/api/thermal/config
  auto thermal_config_post_handler = std::make_shared<HTTPRequestHandler>(
      1 << HTTP_POST, "/api/thermal/config",
      [](httpd_req_t* req) {
        char buf[128] = {};
        int len = std::min((int)req->content_len, (int)sizeof(buf) - 1);
        if (len > 0) httpd_req_recv(req, buf, len);

        JsonDocument doc;
        deserializeJson(doc, buf);
        float slope_deg_per_c = doc["slope_deg_per_c"] |
            (g_thermal_slope_rad_per_k * (180.0f / PI));
        float tref_c = doc["tref_c"] | (g_thermal_ref_temp_k - 273.15f);

        g_thermal_slope_rad_per_k = slope_deg_per_c * (PI / 180.0f);
        g_thermal_ref_temp_k = tref_c + 273.15f;

        Preferences prefs;
        prefs.begin("thermalcomp", false);
        prefs.putFloat("slope", g_thermal_slope_rad_per_k);
        prefs.putFloat("tref_k", g_thermal_ref_temp_k);
        prefs.end();

        ESP_LOGI("eCompass", "Thermal compensation configured: %.4f deg/C, T_ref %.2f C",
                 slope_deg_per_c, tref_c);

        char resp[128];
        snprintf(resp, sizeof(resp),
                 "{\"slope_deg_per_c\":%.4f,\"tref_c\":%.3f}",
                 slope_deg_per_c, tref_c);
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, resp, strlen(resp));
        return ESP_OK;
      });
  sensesp_app->get_http_server()->add_handler(thermal_config_post_handler);

  // ========== ATTITUDE (yaw, pitch, roll) ==========
  auto* sensor_roll = new OrientationValues(
      orientation_sensor, OrientationValues::kRoll);
  auto* sensor_pitch = new OrientationValues(
      orientation_sensor, OrientationValues::kPitch);
  auto* sensor_yaw = new OrientationValues(
      orientation_sensor, OrientationValues::kYaw);

  auto attitude_sensor = std::make_shared<RepeatSensor<AttitudeVector>>(
      ATTITUDE_REPORTING_INTERVAL_MS,
      [sensor_roll, sensor_pitch, sensor_yaw]() {
        return AttitudeVector(sensor_roll->ReportValue(),
                              sensor_pitch->ReportValue(),
                              sensor_yaw->ReportValue());
      });
  auto attitude_sk_output = std::make_shared<SKOutput<AttitudeVector>>(
      kSKPathAttitude, kConfigPathNone);
  attitude_sensor->connect_to(attitude_sk_output);

  // ========== RATE OF TURN ==========
  auto* sensor_turn_rate = new OrientationValues(
      orientation_sensor, OrientationValues::kRateOfTurn);
  auto turn_rate = std::make_shared<RepeatSensor<float>>(
      RATE_REPORTING_INTERVAL_MS,
      [sensor_turn_rate]() { return sensor_turn_rate->ReportValue(); });
  auto metadata_turn_rate = std::make_shared<SKMetadata>();
  metadata_turn_rate->units_ = "rad/s";
  metadata_turn_rate->description_ = "Rate of Turn about mast-keel axis";
  metadata_turn_rate->display_name_ = "Turn Rate";
  metadata_turn_rate->short_name_ = "Turn Rate";
  auto turn_rate_output = std::make_shared<SKOutput<float>>(
      kSKPathTurnRate, "", metadata_turn_rate);
  turn_rate->connect_to(turn_rate_output);

  // ========== MAGNETIC CALIBRATION DIAGNOSTICS ==========
  // MagCalFit: lower % is better, <3.5% is good
  auto* sensor_magcalfit = new OrientationValues(
      orientation_sensor, OrientationValues::kMagCalFitInUse);
  auto magcalfit = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_magcalfit]() { return sensor_magcalfit->ReportValue(); });
  auto magcalfit_metadata = std::make_shared<SKMetadata>();
  magcalfit_metadata->units_ = "%";
  magcalfit_metadata->description_ = "Goodness-of-fit using current Magnetic Calibration";
  magcalfit_metadata->display_name_ = "Mag Cal Fit";
  magcalfit_metadata->short_name_ = "MagFit";
  auto magcalfit_output = std::make_shared<SKOutput<float>>(
      kSKPathMagFit, kConfigPathNone, magcalfit_metadata);
  magcalfit->connect_to(magcalfit_output);

  // MagCalFit Trial
  auto* sensor_magcal_candidate = new OrientationValues(
      orientation_sensor, OrientationValues::kMagCalFitTrial);
  auto magcaltrial = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_magcal_candidate]() { return sensor_magcal_candidate->ReportValue(); });
  auto magcaltrial_metadata = std::make_shared<SKMetadata>();
  magcaltrial_metadata->units_ = "%";
  magcaltrial_metadata->description_ = "Goodness-of-fit using trial Magnetic Calibration";
  magcaltrial_metadata->display_name_ = "Mag Cal Fit Trial";
  magcaltrial_metadata->short_name_ = "MagFitTrial";
  auto magcaltrial_output = std::make_shared<SKOutput<float>>(
      kSKPathMagFitTrial, kConfigPathNone, magcaltrial_metadata);
  magcaltrial->connect_to(magcaltrial_output);

  // Calibration Solver Order [0,4,7,10] - 10 is best
  auto* sensor_cal_order = new OrientationValues(
      orientation_sensor, OrientationValues::kMagCalAlgorithmSolver);
  auto magcalorder = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_cal_order]() { return sensor_cal_order->ReportValue(); });
  auto cal_solver_metadata = std::make_shared<SKMetadata>();
  cal_solver_metadata->units_ = "[0,4,7,10]";
  cal_solver_metadata->description_ = "Calibration algorithm order, 10 is best";
  cal_solver_metadata->display_name_ = "Mag Cal Solver";
  cal_solver_metadata->short_name_ = "Solver";
  auto cal_solver_output = std::make_shared<SKOutput<int>>(
      kSKPathMagSolver, "", cal_solver_metadata);
  magcalorder->connect_to(cal_solver_output);

  // Magnetic Noise - above 0.00056 means unreliable
  auto* sensor_mag_noise = new OrientationValues(
      orientation_sensor, OrientationValues::kMagNoiseCovariance);
  auto magnoise = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_mag_noise]() { return sensor_mag_noise->ReportValue(); });
  auto mag_noise_metadata = std::make_shared<SKMetadata>();
  mag_noise_metadata->units_ = "unitless";
  mag_noise_metadata->description_ = "Magnetic Noise (above 0.00056 = unreliable)";
  mag_noise_metadata->display_name_ = "Mag Noise";
  mag_noise_metadata->short_name_ = "MagNoise";
  auto mag_noise_output = std::make_shared<SKOutput<float>>(
      kSKPathMagNoise, "", mag_noise_metadata);
  magnoise->connect_to(mag_noise_output);

  // Geomagnetic field magnitude (uT) of the calibration currently in use,
  // and of the current (trial) readings. Per the fusion library's own docs
  // (OrientationSensorFusion-ESP wiki: Magnetic-Calibration), comparing
  // these two is the recommended way to tell a genuine magnetic disturbance
  // (B changes) from an ordinary periodic recalibration on stationary data
  // (B stays put but the fit is re-solved anyway).
  auto* sensor_magfield = new OrientationValues(
      orientation_sensor, OrientationValues::kMagFieldMagnitude);
  auto magfield = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_magfield]() { return sensor_magfield->ReportValue(); });
  auto magfield_metadata = std::make_shared<SKMetadata>();
  magfield_metadata->units_ = "uT";
  magfield_metadata->description_ = "Geomagnetic field magnitude of the calibration currently in use";
  magfield_metadata->display_name_ = "Mag Field B";
  magfield_metadata->short_name_ = "MagB";
  auto magfield_output = std::make_shared<SKOutput<float>>(
      kSKPathMagFieldMag, kConfigPathNone, magfield_metadata);
  magfield->connect_to(magfield_output);

  auto* sensor_magfield_trial = new OrientationValues(
      orientation_sensor, OrientationValues::kMagFieldMagnitudeTrial);
  auto magfieldtrial = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_magfield_trial]() { return sensor_magfield_trial->ReportValue(); });
  auto magfieldtrial_metadata = std::make_shared<SKMetadata>();
  magfieldtrial_metadata->units_ = "uT";
  magfieldtrial_metadata->description_ = "Geomagnetic field magnitude from current (trial) readings";
  magfieldtrial_metadata->display_name_ = "Mag Field B Trial";
  magfieldtrial_metadata->short_name_ = "MagBTrial";
  auto magfieldtrial_output = std::make_shared<SKOutput<float>>(
      kSKPathMagFieldMagTrial, kConfigPathNone, magfieldtrial_metadata);
  magfieldtrial->connect_to(magfieldtrial_output);

  // Geomagnetic inclination (rad) -- another interference indicator per the
  // fusion library docs: a swing of >~10 deg from recent values indicates a
  // magnetic disturbance rather than an ordinary recalibration.
  auto* sensor_maginclination = new OrientationValues(
      orientation_sensor, OrientationValues::kMagInclination);
  auto maginclination = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_maginclination]() { return sensor_maginclination->ReportValue(); });
  auto maginclination_metadata = std::make_shared<SKMetadata>();
  maginclination_metadata->units_ = "rad";
  maginclination_metadata->description_ = "Geomagnetic field inclination from horizontal";
  maginclination_metadata->display_name_ = "Mag Inclination";
  maginclination_metadata->short_name_ = "MagIncl";
  auto maginclination_output = std::make_shared<SKOutput<float>>(
      kSKPathMagInclination, kConfigPathNone, maginclination_metadata);
  maginclination->connect_to(maginclination_output);

  // Calibrated geomagnetic field vector (uT), sensor/boat-frame axes (bow,
  // starboard, down) -- not heading-compensated. Published at
  // MAG_VECTOR_REPORTING_INTERVAL_MS (1 Hz) per TODO.md "eCompass DC
  // Hard-Iron Drift" and handoffs/magnoise-instrumentation.md: averaged
  // over a window, the mean gives the DC disturbance vector directly
  // (previously back-solved from B-magnitude + inclination); the per-axis
  // std-dev gives the AC noise direction/frequency work. Requires the
  // LOCAL PATCH to OrientationSensorFusion-ESP (see README.md "Local
  // OrientationSensorFusion-ESP Patches") -- SignalK-Orientation's
  // OrientationValues wrapper has no vector accessor, so these call
  // sensor_interface_ directly instead of going through OrientationValues.
  auto magfieldvector_x = std::make_shared<RepeatSensor<float>>(
      MAG_VECTOR_REPORTING_INTERVAL_MS, [orientation_sensor]() {
        return orientation_sensor->sensor_interface_->GetMagneticBcX();
      });
  auto magfieldvector_x_metadata = std::make_shared<SKMetadata>();
  magfieldvector_x_metadata->units_ = "uT";
  magfieldvector_x_metadata->description_ =
      "Calibrated geomagnetic field vector, bow-axis (X) component";
  magfieldvector_x_metadata->display_name_ = "Mag Field Bc X";
  magfieldvector_x_metadata->short_name_ = "BcX";
  auto magfieldvector_x_output = std::make_shared<SKOutput<float>>(
      kSKPathMagFieldVectorX, kConfigPathNone, magfieldvector_x_metadata);
  magfieldvector_x->connect_to(magfieldvector_x_output);

  auto magfieldvector_y = std::make_shared<RepeatSensor<float>>(
      MAG_VECTOR_REPORTING_INTERVAL_MS, [orientation_sensor]() {
        return orientation_sensor->sensor_interface_->GetMagneticBcY();
      });
  auto magfieldvector_y_metadata = std::make_shared<SKMetadata>();
  magfieldvector_y_metadata->units_ = "uT";
  magfieldvector_y_metadata->description_ =
      "Calibrated geomagnetic field vector, starboard-axis (Y) component";
  magfieldvector_y_metadata->display_name_ = "Mag Field Bc Y";
  magfieldvector_y_metadata->short_name_ = "BcY";
  auto magfieldvector_y_output = std::make_shared<SKOutput<float>>(
      kSKPathMagFieldVectorY, kConfigPathNone, magfieldvector_y_metadata);
  magfieldvector_y->connect_to(magfieldvector_y_output);

  auto magfieldvector_z = std::make_shared<RepeatSensor<float>>(
      MAG_VECTOR_REPORTING_INTERVAL_MS, [orientation_sensor]() {
        return orientation_sensor->sensor_interface_->GetMagneticBcZ();
      });
  auto magfieldvector_z_metadata = std::make_shared<SKMetadata>();
  magfieldvector_z_metadata->units_ = "uT";
  magfieldvector_z_metadata->description_ =
      "Calibrated geomagnetic field vector, down-axis (Z) component";
  magfieldvector_z_metadata->display_name_ = "Mag Field Bc Z";
  magfieldvector_z_metadata->short_name_ = "BcZ";
  auto magfieldvector_z_output = std::make_shared<SKOutput<float>>(
      kSKPathMagFieldVectorZ, kConfigPathNone, magfieldvector_z_metadata);
  magfieldvector_z->connect_to(magfieldvector_z_output);

  // ========== MAG CAL CHANGE DETECTOR ==========
  // Watches magfit (the in-use fit error) for any single-interval change
  // bigger than the library's own aging drift can explain. Aging adds
  // ~1%/24h (FITERRORAGINGSECS in magnetic.c), which works out to a few
  // thousandths of a percent per CALIBRATION_REPORTING_INTERVAL_MS tick --
  // so any change past kMagCalJumpThresholdPct can only be a fresh
  // calibration-acceptance event, not aging noise. When one fires, this
  // records how big the fit change was and how many degrees the reported
  // heading moved as a result, so a silent recalibration shows up in
  // Grafana instead of just looking like the boat swung.
  const float kMagCalJumpThresholdPct = 0.01f;
  event_loop()->onRepeat(CALIBRATION_REPORTING_INTERVAL_MS,
      [sensor_magcalfit, sensor_heading, kMagCalJumpThresholdPct]() {
        static float last_fit = -1.0f;
        static float last_heading_deg = NAN;

        float fit = sensor_magcalfit->ReportValue();
        float heading_deg = sensor_heading->ReportValue() * (180.0f / PI);

        // Skip the first sample (nothing to compare yet) and the fusion
        // library's startup sentinel (0 = insufficient data for a fit).
        if (last_fit >= 0.0f && fit > 0.0f) {
          float fit_delta = fit - last_fit;
          if (fabsf(fit_delta) > kMagCalJumpThresholdPct) {
            float heading_delta = heading_deg - last_heading_deg;
            while (heading_delta > 180.0f) heading_delta -= 360.0f;
            while (heading_delta < -180.0f) heading_delta += 360.0f;
            g_magcal_event_fitdelta_pct = fit_delta;
            g_magcal_event_headingdelta_deg = heading_delta;
            ESP_LOGW("eCompass",
                "Magnetic calibration changed: fit %.3f%% -> %.3f%% (%+.3f%%), "
                "heading shifted %+.1f deg",
                last_fit, fit, fit_delta, heading_delta);
          }
        }
        last_fit = fit;
        last_heading_deg = heading_deg;
      });

  auto magcal_event_fitdelta = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      []() { return g_magcal_event_fitdelta_pct; });
  auto magcal_event_fitdelta_metadata = std::make_shared<SKMetadata>();
  magcal_event_fitdelta_metadata->units_ = "%";
  magcal_event_fitdelta_metadata->description_ =
      "Fit-error change of the most recent auto-accepted magnetic calibration event (holds until the next event)";
  magcal_event_fitdelta_metadata->display_name_ = "Last MagCal Event Fit Delta";
  magcal_event_fitdelta_metadata->short_name_ = "MagCalEvtFit";
  auto magcal_event_fitdelta_output = std::make_shared<SKOutput<float>>(
      kSKPathMagCalEventFit, kConfigPathNone, magcal_event_fitdelta_metadata);
  magcal_event_fitdelta->connect_to(magcal_event_fitdelta_output);

  auto magcal_event_headingdelta = std::make_shared<RepeatSensor<float>>(
      CALIBRATION_REPORTING_INTERVAL_MS,
      []() { return g_magcal_event_headingdelta_deg; });
  auto magcal_event_headingdelta_metadata = std::make_shared<SKMetadata>();
  magcal_event_headingdelta_metadata->units_ = "deg";
  magcal_event_headingdelta_metadata->description_ =
      "Approximate heading shift caused by the most recent auto-accepted magnetic calibration event (holds until the next event)";
  magcal_event_headingdelta_metadata->display_name_ = "Last MagCal Event Heading Delta";
  magcal_event_headingdelta_metadata->short_name_ = "MagCalEvtHdg";
  auto magcal_event_headingdelta_output = std::make_shared<SKOutput<float>>(
      kSKPathMagCalEventHeading, kConfigPathNone, magcal_event_headingdelta_metadata);
  magcal_event_headingdelta->connect_to(magcal_event_headingdelta_output);

  // ========== MAG CAL SAVE BUTTON ==========
  auto* button_watcher = new DigitalInputChange(
      PIN_SWITCH_CAL_SAVE, INPUT_PULLUP, CHANGE, kConfigPathNone);
  const int kDebounceDelay = 350;
  auto* debounce = new DebounceInt(kDebounceDelay, "/debounce/delay");
  ConfigItem(debounce)
      ->set_title("MagCal Button Debounce")
      ->set_description("Debounce delay (ms) for Magnetic Calibration save button")
      ->set_sort_order(1000);

  auto save_mcal_function = [orientation_sensor](int input) {
    if (input == SWITCH_ACTIVE_STATE) {
      orientation_sensor->sensor_interface_->SaveMagneticCalibration();
      ESP_LOGI("eCompass", "Magnetic Calibration saved to NVS");
    }
  };
  auto* button_consumer = new LambdaConsumer<int>(save_mcal_function);
  button_watcher->connect_to(debounce)->connect_to(button_consumer);

  // HTTP endpoint: save magnetic calibration.
  // Usage (from boat-panel): POST http://sensesp.local/api/calibration/save-mag
  auto save_cal_handler = std::make_shared<HTTPRequestHandler>(
      1 << HTTP_POST, "/api/calibration/save-mag",
      [orientation_sensor](httpd_req_t* req) {
        orientation_sensor->sensor_interface_->SaveMagneticCalibration();
        ESP_LOGI("eCompass", "Magnetic Calibration saved to NVS (via HTTP)");
        httpd_resp_set_type(req, "text/plain");
        httpd_resp_send(req, "Magnetic calibration saved", 0);
        return ESP_OK;
      });
  sensesp_app->get_http_server()->add_handler(save_cal_handler);

  // ========== POWER MONITORING (INA226/INA228) ==========
  // Battery sensor at 0x41: INA228 (see USE_INA228), external 20A/75mV shunt
  // Solar sensor at 0x40: INA226, onboard R002 2mΩ shunt (bench config)
  // Both share the existing I2C bus — no additional Wire.begin() needed.
  //
  // Current sign convention: verify after installation.
  // Positive = charging when shunt IN+ faces battery, IN- faces bus bar.
  // Swap IN+/IN- in hardware (no code change) if sign is reversed.

#ifdef USE_INA228
  auto* ina_battery = new INA228(INA_BATTERY_I2C_ADDR);
#else
  auto* ina_battery = new INA226(INA_BATTERY_I2C_ADDR);
#endif
  bool ina_battery_ok = ina_battery->begin();
  if (!ina_battery_ok) {
    ESP_LOGE("eCompass", "Battery INA sensor (0x%02X) not found on I2C bus",
             INA_BATTERY_I2C_ADDR);
  } else {
    ina_battery->setMaxCurrentShunt(INA_MAX_AMPS, INA_BATTERY_SHUNT_OHMS);
    ESP_LOGI("eCompass", "Battery INA sensor OK (0x%02X)", INA_BATTERY_I2C_ADDR);
  }

  auto* ina_solar = new INA226(INA_SOLAR_I2C_ADDR);
  bool ina_solar_ok = ina_solar->begin();
  if (!ina_solar_ok) {
    ESP_LOGE("eCompass", "Solar INA sensor (0x%02X) not found on I2C bus",
             INA_SOLAR_I2C_ADDR);
  } else {
    ina_solar->setMaxCurrentShunt(INA_MAX_AMPS, INA_SOLAR_SHUNT_OHMS);
    ESP_LOGI("eCompass", "Solar INA sensor OK (0x%02X)", INA_SOLAR_I2C_ADDR);
  }

  // --- Battery: voltage, current, power ---
  auto bat_voltage = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_battery, ina_battery_ok]() -> float {
        if (!ina_battery_ok) return NAN;
        return static_cast<float>(ina_battery->getBusVoltage());
      });
  auto bat_voltage_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.voltage", "");
  bat_voltage->connect_to(bat_voltage_out);

  auto bat_current = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_battery, ina_battery_ok]() -> float {
        if (!ina_battery_ok) return NAN;
        return static_cast<float>(ina_battery->getCurrent());
      });
  auto bat_current_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.current", "");
  bat_current->connect_to(bat_current_out);

  auto bat_power = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_battery, ina_battery_ok]() -> float {
        if (!ina_battery_ok) return NAN;
        return static_cast<float>(ina_battery->getCurrent() * ina_battery->getBusVoltage());
      });
  auto bat_power_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.power", "");
  bat_power->connect_to(bat_power_out);

#ifdef USE_INA228
  // INA228 hardware accumulation registers — converted to remaining Ah/Wh/SoC.
  // After "set full", accumulators start at zero and go negative as the battery
  // discharges (assuming correct shunt orientation — see sign convention note above).
  //
  // remaining_Ah = nominal_Ah + accumulated_C / 3600
  // remaining_Wh = nominal_Wh + accumulated_J / 3600
  // SoC          = remaining_Ah / nominal_Ah  (clamped 0–1)

  // remaining Ah → electrical.batteries.house.capacity.remaining
  auto bat_remaining_ah = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_battery, ina_battery_ok]() -> float {
        if (!ina_battery_ok) return NAN;
        float accumulated_ah = static_cast<float>(ina_battery->getCharge()) / 3600.0f;
        return g_battery_seed_ah + accumulated_ah;
      });
  auto bat_remaining_ah_meta = std::make_shared<SKMetadata>();
  bat_remaining_ah_meta->units_ = "Ah";
  bat_remaining_ah_meta->display_name_ = "Remaining Charge";
  bat_remaining_ah_meta->short_name_ = "Remaining Ah";
  auto bat_remaining_ah_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.capacity.remaining", "", bat_remaining_ah_meta);
  bat_remaining_ah->connect_to(bat_remaining_ah_out);

  // remaining Wh → electrical.batteries.house.energy
  auto bat_remaining_wh = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_battery, ina_battery_ok]() -> float {
        if (!ina_battery_ok) return NAN;
        float accumulated_wh = static_cast<float>(ina_battery->getEnergy()) / 3600.0f;
        return (g_battery_seed_ah * g_battery_nominal_v) + accumulated_wh;
      });
  auto bat_remaining_wh_meta = std::make_shared<SKMetadata>();
  bat_remaining_wh_meta->units_ = "Wh";
  bat_remaining_wh_meta->display_name_ = "Remaining Energy";
  bat_remaining_wh_meta->short_name_ = "Remaining Wh";
  auto bat_remaining_wh_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.energy", "", bat_remaining_wh_meta);
  bat_remaining_wh->connect_to(bat_remaining_wh_out);

  // SoC ratio (0–1) → electrical.batteries.house.capacity.stateOfCharge
  auto bat_soc = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_battery, ina_battery_ok]() -> float {
        if (!ina_battery_ok) return NAN;
        float accumulated_ah = static_cast<float>(ina_battery->getCharge()) / 3600.0f;
        float soc = (g_battery_seed_ah + accumulated_ah) / g_battery_capacity_ah;
        return fmaxf(0.0f, fminf(1.0f, soc));  // clamp 0-1
      });
  auto bat_soc_meta = std::make_shared<SKMetadata>();
  bat_soc_meta->units_ = "ratio";
  bat_soc_meta->display_name_ = "State of Charge";
  bat_soc_meta->short_name_ = "SoC";
  auto bat_soc_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.capacity.stateOfCharge", "", bat_soc_meta);
  bat_soc->connect_to(bat_soc_out);

  // Full-charge detector observability, published to Signal K so historic
  // detector behavior is queryable from the same InfluxDB history already
  // used for electrical.batteries.house.{voltage,current} — see the
  // diagnostic method in docs/battery-soc-persistence-handoff.md. Without
  // this, the detector's state is only ever visible at the instant you poll
  // it, and the latch's own hysteresis reset erases any earlier trigger by
  // the time the next discharge cycle begins.
  auto full_charge_pass_ratio_sensor = std::make_shared<RepeatSensor<float>>(
      FULL_CHARGE_SAMPLE_INTERVAL_MS,
      []() -> float { return GetFullChargePassRatio(); });
  auto full_charge_pass_ratio_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.fullChargeDetector.passRatio", "");
  full_charge_pass_ratio_sensor->connect_to(full_charge_pass_ratio_out);

  auto full_charge_latched_sensor = std::make_shared<RepeatSensor<bool>>(
      FULL_CHARGE_SAMPLE_INTERVAL_MS,
      []() -> bool { return full_charge_latched; });
  auto full_charge_latched_out = std::make_shared<SKOutput<bool>>(
      "electrical.batteries.house.fullChargeDetector.latched", "");
  full_charge_latched_sensor->connect_to(full_charge_latched_out);

  // HTTP endpoint: return current NVS battery config (capacity, seed, nominal voltage),
  // plus live full-charge detector status (see docs/battery-soc-persistence-handoff.md) —
  // lets a real-world soak test be observed over HTTP instead of requiring serial/USB access.
  // Usage: GET http://sensesp.local/api/battery/config
  auto config_get_handler = std::make_shared<HTTPRequestHandler>(
      1 << HTTP_GET, "/api/battery/config",
      [](httpd_req_t* req) {
        float pass_ratio = GetFullChargePassRatio();
        char resp[256];
        snprintf(resp, sizeof(resp),
                 "{\"capacity_ah\":%.1f,\"seed_ah\":%.1f,\"nominal_v\":%.1f,"
                 "\"full_charge_pass_ratio\":%.3f,\"full_charge_latched\":%s}",
                 g_battery_capacity_ah, g_battery_seed_ah, g_battery_nominal_v,
                 pass_ratio, full_charge_latched ? "true" : "false");
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, resp, strlen(resp));
        return ESP_OK;
      });
  sensesp_app->get_http_server()->add_handler(config_get_handler);

  // HTTP endpoint: seed battery SOC and update capacity/voltage from boat-panel.
  // Body (all fields optional — omitting keeps the current NVS value):
  //   {"capacity_ah": 100, "soc": 0.85, "nominal_v": 12.8}
  // Updates NVS, resets INA228 accumulators, returns JSON confirmation.
  // Usage: POST http://sensesp.local/api/battery/configure
  auto configure_handler = std::make_shared<HTTPRequestHandler>(
      1 << HTTP_POST, "/api/battery/configure",
      [ina_battery, ina_battery_ok](httpd_req_t* req) {
        if (!ina_battery_ok) {
          httpd_resp_set_status(req, "503 Service Unavailable");
          httpd_resp_set_type(req, "text/plain");
          httpd_resp_send(req, "Battery sensor not available", 0);
          return ESP_OK;
        }
        char buf[256] = {};
        int len = std::min((int)req->content_len, (int)sizeof(buf) - 1);
        if (len > 0) httpd_req_recv(req, buf, len);

        JsonDocument doc;
        deserializeJson(doc, buf);
        float capacity_ah = doc["capacity_ah"] | g_battery_capacity_ah;
        float soc         = doc["soc"]         | 1.0f;
        float nominal_v   = doc["nominal_v"]   | g_battery_nominal_v;

        g_battery_capacity_ah = capacity_ah;
        g_battery_nominal_v   = nominal_v;
        g_battery_seed_ah     = capacity_ah * soc;

        Preferences prefs;
        prefs.begin("battery", false);
        prefs.putFloat("capacity_ah", g_battery_capacity_ah);
        prefs.putFloat("nominal_v",   g_battery_nominal_v);
        prefs.putFloat("seed_ah",     g_battery_seed_ah);
        prefs.end();

        ina_battery->setAccumulation(1);
        ESP_LOGI("eCompass", "Battery configured: %.1f Ah cap, SoC %.2f → %.1f Ah seed",
                 capacity_ah, soc, g_battery_seed_ah);

        char resp[128];
        snprintf(resp, sizeof(resp),
                 "{\"capacity_ah\":%.1f,\"soc\":%.3f,\"seed_ah\":%.1f,\"nominal_v\":%.1f}",
                 g_battery_capacity_ah, soc, g_battery_seed_ah, g_battery_nominal_v);
        httpd_resp_set_type(req, "application/json");
        httpd_resp_send(req, resp, strlen(resp));
        return ESP_OK;
      });
  sensesp_app->get_http_server()->add_handler(configure_handler);

  // Periodic NVS checkpoint — bounds SoC staleness after an unplanned power
  // loss to at most CHECKPOINT_INTERVAL_MS. Mirrors /api/battery/configure's
  // persistence logic. Does not correct drift — see full-charge detector below.
  event_loop()->onRepeat(CHECKPOINT_INTERVAL_MS, [ina_battery, ina_battery_ok]() {
    if (!ina_battery_ok) return;
    float accumulated_ah = static_cast<float>(ina_battery->getCharge()) / 3600.0f;
    float remaining_ah = g_battery_seed_ah + accumulated_ah;

    Preferences prefs;
    prefs.begin("battery", false);
    prefs.putFloat("seed_ah", remaining_ah);
    prefs.end();

    g_battery_seed_ah = remaining_ah;
    ina_battery->setAccumulation(1);
    ESP_LOGI("eCompass", "Battery checkpoint: %.2f Ah seed persisted", remaining_ah);
  });

  // Automated full-charge detection — the anti-drift complement to the
  // periodic checkpoint above. See docs/battery-soc-persistence-handoff.md
  // for the threshold/dwell-time rationale and tradeoffs.
  event_loop()->onRepeat(FULL_CHARGE_SAMPLE_INTERVAL_MS, [ina_battery, ina_battery_ok]() {
    if (!ina_battery_ok) return;

    float voltage = static_cast<float>(ina_battery->getBusVoltage());
    float current = static_cast<float>(ina_battery->getCurrent());
    bool sample_passes = (voltage >= FULL_CHARGE_VOLTAGE_THRESHOLD_V) &&
                          (fabsf(current) <= FULL_CHARGE_CURRENT_THRESHOLD_A);

    bool &slot = full_charge_samples[full_charge_sample_idx];
    if (full_charge_samples_filled >= FULL_CHARGE_WINDOW_SAMPLES) {
      if (slot) full_charge_pass_count--;
    } else {
      full_charge_samples_filled++;
    }
    slot = sample_passes;
    if (slot) full_charge_pass_count++;
    full_charge_sample_idx = (full_charge_sample_idx + 1) % FULL_CHARGE_WINDOW_SAMPLES;

    // New discharge cycle started — allow the detector to fire again next time.
    if (voltage < FULL_CHARGE_RESET_VOLTAGE_V) {
      full_charge_latched = false;
    }

    if (full_charge_latched) return;
    if (full_charge_samples_filled < FULL_CHARGE_WINDOW_SAMPLES) return;

    float pass_ratio = static_cast<float>(full_charge_pass_count) / FULL_CHARGE_WINDOW_SAMPLES;
    if (pass_ratio >= FULL_CHARGE_PASS_RATIO) {
      g_battery_seed_ah = g_battery_capacity_ah;
      Preferences prefs;
      prefs.begin("battery", false);
      prefs.putFloat("seed_ah", g_battery_seed_ah);
      prefs.end();
      ina_battery->setAccumulation(1);
      full_charge_latched = true;
      ESP_LOGI("eCompass",
               "Auto full-charge detected (%.0f%% of window passed) — SoC seeded to 100%% (%.1f Ah)",
               pass_ratio * 100.0f, g_battery_seed_ah);
    }
  });
#endif

  // --- Solar: voltage, current, power ---
  auto sol_voltage = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_solar, ina_solar_ok]() -> float {
        if (!ina_solar_ok) return NAN;
        return static_cast<float>(ina_solar->getBusVoltage());
      });
  auto sol_voltage_out = std::make_shared<SKOutput<float>>(
      "electrical.solar.voltage", "");
  sol_voltage->connect_to(sol_voltage_out);

  auto sol_current = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_solar, ina_solar_ok]() -> float {
        if (!ina_solar_ok) return NAN;
        return static_cast<float>(ina_solar->getCurrent());
      });
  auto sol_current_out = std::make_shared<SKOutput<float>>(
      "electrical.solar.current", "");
  sol_current->connect_to(sol_current_out);

  auto sol_power = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_solar, ina_solar_ok]() -> float {
        if (!ina_solar_ok) return NAN;
        return static_cast<float>(ina_solar->getCurrent() * ina_solar->getBusVoltage());
      });
  auto sol_power_out = std::make_shared<SKOutput<float>>(
      "electrical.solar.power", "");
  sol_power->connect_to(sol_power_out);

  // Prevent shared_ptr garbage collection
  while (true) {
    loop();
  }
}

void loop() { event_loop()->tick(); }
