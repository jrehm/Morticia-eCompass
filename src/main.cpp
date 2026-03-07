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

// For temperature calibration
#include "sensesp/transforms/linear.h"

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

// Connectivity watchdog: reboot ESP32 if Signal K connection
// is lost for this many milliseconds. Handles edge cases where
// the SKWSClient retry loop gets stuck in a non-disconnected
// state (e.g., after Signal K server restart).
#define SK_CONNECTION_TIMEOUT_MS (60 * 1000)  // 60 seconds

// Hardware watchdog: reboot if main loop stalls completely.
// This catches hard lockups (I2C bus hang, stack overflow, etc.)
#define HW_WATCHDOG_TIMEOUT_S (120)  // 2 minutes

using namespace sensesp;

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
      ->get_app();

  // Override the auto-generated UUID clientId with a human-readable name.
  // SK source keys appear as ws.<clientId>.* — this keeps them human-readable.
  // set_client_id() is a local patch to SKWSClient (see DECISIONS.md ADR-005).
  // reset_auth_token() was used once for initial re-registration; not needed ongoing.
  sensesp_app->get_ws_client()->set_client_id("SensESP");
  ESP_LOGI("eCompass", "SK client_id set to: SensESP");

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
  const char* kConfigPathNone = "";

  // ---- Initialize Orientation Sensor ----
  auto* orientation_sensor = new OrientationSensor(
      PIN_I2C_SDA, PIN_I2C_SCL, BOARD_ACCEL_MAG_I2C_ADDR, BOARD_GYRO_I2C_ADDR);
  const int fusionIntervalMs = 1000 / orientation_sensor->GetFusionRateHz();
  event_loop()->onRepeat(fusionIntervalMs,
      [orientation_sensor]() { orientation_sensor->ReadAndProcessSensors(); });

  // ========== COMPASS HEADING ==========
  auto* sensor_heading = new OrientationValues(
      orientation_sensor, OrientationValues::kCompassHeading);
  auto compass_heading = std::make_shared<RepeatSensor<float>>(
      ORIENTATION_REPORTING_INTERVAL_MS,
      [sensor_heading]() { return sensor_heading->ReportValue(); });

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

  compass_heading
      ->connect_to(mountingOffset)
      ->connect_to(compass_sk_output)
      ->connect_to(deviationInterpolator)
      ->connect_to(new AngleCorrection(0.0, 0.0, kConfigPathNone))
      ->connect_to(magneticheading_sk_output);

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
        return static_cast<float>(ina_battery->getPower());
      });
  auto bat_power_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.power", "");
  bat_power->connect_to(bat_power_out);

#ifdef USE_INA228
  // INA228 hardware accumulation registers
  // getEnergy() → Joules (J), getCharge() → Coulombs (C) — both SI units for Signal K
  //
  // TODO (first power-up with INA228 fitted): decide on accumulator reset strategy.
  // The INA228 accumulators reset on every power cycle, so they start from zero
  // automatically. However, if you want a known reference point (e.g., a full
  // charge = 0 Ah discharged), add this call before the RepeatSensor setup:
  //   if (ina_battery_ok) ina_battery->resetAccumulators();
  // Without this, accumulators reflect only what has happened since last reboot.
  auto bat_energy = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_battery, ina_battery_ok]() -> float {
        if (!ina_battery_ok) return NAN;
        return static_cast<float>(ina_battery->getEnergy());  // J
      });
  auto bat_energy_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.energy", "");
  bat_energy->connect_to(bat_energy_out);

  auto bat_charge = std::make_shared<RepeatSensor<float>>(
      POWER_REPORTING_INTERVAL_MS,
      [ina_battery, ina_battery_ok]() -> float {
        if (!ina_battery_ok) return NAN;
        return static_cast<float>(ina_battery->getCharge());  // C
      });
  auto bat_charge_out = std::make_shared<SKOutput<float>>(
      "electrical.batteries.house.capacity", "");
  bat_charge->connect_to(bat_charge_out);
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
        return static_cast<float>(ina_solar->getPower());
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
