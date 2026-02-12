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

using namespace sensesp;

// Deviation Table - enter via web UI or hard-code after compass swing
class DeviationInterpolator : public CurveInterpolator {
 public:
  DeviationInterpolator(String config_path = "")
      : CurveInterpolator(NULL, config_path) {
    // Default: no deviation correction
    // After swing, uncomment and populate:
    //   clear_samples();
    //   add_sample(CurveInterpolator::Sample(0.0, 0.0));
    //   add_sample(CurveInterpolator::Sample(6.283, 6.283));
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
      ->set_hostname("morticia-ecompass")
      //->set_wifi_client("YourSSID", "YourPassword")
      //->set_sk_server("10.10.10.1", 3000)
      ->enable_uptime_sensor()
      ->enable_ip_address_sensor()
      ->enable_free_mem_sensor()
      ->enable_system_hz_sensor()
      ->get_app();

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

  // Prevent shared_ptr garbage collection
  while (true) {
    loop();
  }
}

void loop() { event_loop()->tick(); }
