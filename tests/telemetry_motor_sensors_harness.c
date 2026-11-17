/* Production sensor readiness with electrical gating disabled; no hardware. */
#include <assert.h>
#include "../ADS/Core/Src/ads_sensors.c"
static uint32_t tick=100;
uint32_t HAL_GetTick(void) { return tick; }
int ADS_Motor_PowerState(void) { return 0; }
int main(void)
{
  _Static_assert(!ADS_ELECTRICAL_LIMITS_ENABLED,"Telemetry policy required");
  _Static_assert(ADS_BOARD_ACCEPTED,"Electrical calibration must not gate output");
  ADS_Sensors_Init();
  /* Missing sensor readings remain invalid; they do not authorize control. */
  assert(!cache.channels[0].valid);
  assert(ADS_Motor_IdleReady() && ADS_Motor_ProtectionReady());
  for(unsigned i=0;i<3;i++) cache.channels[i]=(ADS_Sample){999999,0,1};
  tick=10000;
  assert(ADS_Motor_IdleReady() && ADS_Motor_ProtectionReady());
  assert(ADS_Motor_PowerSampleState(tick)==0);
  tick+=49;assert(ADS_Motor_PowerSampleState(10000)==0);
  tick++;assert(ADS_Motor_PowerSampleState(10000)==1);
  tick=25;assert(ADS_Motor_PowerSampleState(UINT32_MAX-24)==1);
  tick=10000;
  ADS_Sample out[5]; ADS_Sensors_Acquire(out,0);
  assert(!out[0].valid); /* Stale telemetry is not rewritten as valid zero. */
  return 0;
}
