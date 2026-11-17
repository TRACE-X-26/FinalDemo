/* Backend compatibility fixture: production protocol/state machine, fake IO.
 * No USB, GPIO, relay or real sensor is accessed by this executable. */
#include "ads_protocol.h"
#include "ads_board_config.h"
#include "ads_motor.h"
#include "ads_acquisition.h"
#include "ads_protection.h"
#include <stdio.h>
#include <string.h>

static ADS_Test motor;
static ADS_Acquisition samples;
static unsigned powered;
static uint32_t powered_ms;
static int supply_missing;
static int complete_on_measure;
static const char *mode;
static uint32_t clock_offset;
static uint32_t fixture_tick;
static uint32_t tick(void *ctx)
{
  (void)ctx; return fixture_tick+clock_offset;
}
static int transmit(const uint8_t *data,size_t size,void *ctx)
{ (void)ctx; return fwrite(data,1,size,stdout)==size?0:-1; }
static int ready(void *ctx) { (void)ctx; return 1; }
static void stop(void *ctx) { (void)ctx; powered=0; }
static int prepare(void *ctx)
{ (void)ctx; powered=1; powered_ms=tick(NULL); return 1; }
static int power_state(void *ctx)
{
  (void)ctx; uint32_t age=tick(NULL)-powered_ms;
  if(age>=ADS_POWER_CHECK_TIMEOUT_MS) return 0;
  ADS_Sample out[5]; ADS_Acquisition_Snapshot(&samples,out,tick(NULL));
  int state=ADS_Protection_DownstreamSample(out,samples.info.electrical_started_ms,powered_ms,tick(NULL));
  return state<0?0:state==1?2:1;
}
static int start(uint32_t pwm,uint32_t duration,void *ctx)
{ (void)ctx; return powered && pwm==ADS_BENCH_PWM_PERCENT && duration<=ADS_BENCH_MAX_DURATION_MS; }
static void acquire(ADS_Sample out[5],void *ctx)
{ (void)ctx; ADS_Acquisition_Snapshot(&samples,out,tick(NULL)); }
static void info(ADS_MeasurementInfo *out,void *ctx)
{ (void)ctx; *out=samples.info; }
static void update(void)
{
  uint32_t now=tick(NULL);
  uint16_t bus=powered && !supply_missing?(3000U<<3)|2U:2U;
  if(!strcmp(mode,"high-voltage"))bus=(5000U<<3)|2U;
  if(!strcmp(mode,"powered-idle"))bus=(3000U<<3)|2U;
  uint32_t captured=!strcmp(mode,"stale-electrical")?now-2000U:now;
  ADS_Acquisition_Electrical(&samples,bus,!strcmp(mode,"high-current")?30000:motor.running?1000:0,
      100,strcmp(mode,"invalid-electrical")!=0,captured,captured,1);
  ADS_Acquisition_Encoder(&samples,motor.running?1:0,100,11,34,1,1,now,0);
}
int main(int argc,char **argv)
{
  _Static_assert(ADS_BOARD_ACCEPTED,"Fixture must use canonical operator profile");
  setvbuf(stdout,NULL,_IONBF,0);
  mode=argc>1?argv[1]:"normal";
  supply_missing=argc>1 && !strcmp(argv[1],"missing-supply");
  complete_on_measure=argc>1 && !strcmp(argv[1],"complete-on-measure");
  ADS_Acquisition_Init(&samples);
  ADS_Test_Init(&motor,ADS_BENCH_PWM_PERCENT,ADS_BENCH_MAX_DURATION_MS,
                ADS_BOARD_ACCEPTED,ready,start,stop,NULL);
  motor.power_required=1; motor.prepare_power=prepare; motor.power_state=power_state;
  motor.supervised_required=ADS_MOTOR_OPERATING_MODE==ADS_MODE_SUPERVISED_TEST;
  motor.power_feedback_installed=ADS_POWER_FEEDBACK_INSTALLED;
  ADS_Protocol protocol;
  ADS_Protocol_Init(&protocol,transmit,tick,NULL); protocol.require_crc=1;
  ADS_Protocol_SetHardwareCallbacks(&protocol,acquire,stop);
  ADS_Protocol_SetMeasurementInfo(&protocol,info);
  ADS_Protocol_SetMotorTest(&protocol,&motor);
  char frame[1024];
  while(fgets(frame,sizeof(frame),stdin)) {
    /* Out-of-band fixture clock; these lines are never protocol commands. */
    unsigned timestamp;
    if(sscanf(frame,"FIXTURE_TICK %u",&timestamp)==1) { fixture_tick=timestamp; continue; }
    /* Deterministically exercise a sample racing with normal relay shutdown. */
    if(complete_on_measure && motor.running && strstr(frame,"READ_MEASUREMENTS"))
      clock_offset+=motor.duration_ms;
    ADS_Protocol_Poll(&protocol); update();
    for(size_t i=0;frame[i];i++) ADS_Protocol_ProcessByte(&protocol,(uint8_t)frame[i]);
  }
  return 0;
}
