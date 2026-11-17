#include "ads_probe.h"
#include <string.h>
#define PROBE_PERIOD_MS 100U
#define PROBE_TIMEOUT_MS 20U
#define PROBE_STALE_MS 500U
#define PROBE_AVERAGE_COUNT 4U
static ADS_ProbeIO io;
static ADS_ProbeConfig config;
static ADS_ProbeMeasurement latest;
static uint32_t last_attempt,conversion_started,sum;
static uint8_t initialized,pending,count,attempted;

static int config_valid(const ADS_ProbeConfig *c)
{
  return c && c->reference_mv>=2500 && c->reference_mv<=3600 &&
    c->divider_num>0 && c->divider_num<=1000000 && c->divider_den>0 && c->divider_den<=1000000 &&
    c->divider_num>=c->divider_den && c->divider_num<=10U*c->divider_den &&
    c->gain_ppm>=500000 && c->gain_ppm<=1500000 &&
    c->offset_mv>=-1000 && c->offset_mv<=1000 && c->max_voltage_mv>0 && c->max_voltage_mv<=12000;
}
int ADS_Probe_Convert(uint16_t raw,const ADS_ProbeConfig *c,ADS_ProbeMeasurement *out)
{
  memset(out,0,sizeof(*out)); out->status="ADC_READ_ERROR";
  if(!config_valid(c) || raw>4095U) return 0;
  out->raw_adc=raw; out->raw_valid=1; out->calibrated=c->calibrated;
  out->adc_pin_uv=(uint32_t)(((uint64_t)raw*c->reference_mv*1000U+2047U)/4095U);
  int64_t input_uv=((int64_t)out->adc_pin_uv*c->divider_num+c->divider_den/2)/c->divider_den;
  out->voltage_mv=(int32_t)((input_uv*c->gain_ppm+500000000)/1000000000)+c->offset_mv;
  /* One input-referred ADC count accommodates endpoint quantization only. */
  uint32_t quantum=(c->reference_mv*c->divider_num+4095U*c->divider_den-1U)/(4095U*c->divider_den);
  if(raw>=4080U || out->voltage_mv<0 || out->voltage_mv>(int32_t)(c->max_voltage_mv+quantum)) {
    out->status="OUT_OF_RANGE"; return 0;
  }
  out->valid=1; out->status="OK"; return 1;
}
static void failed(const char *status,uint32_t now)
{
  if(io.stop) io.stop(io.context);
  memset(&latest,0,sizeof(latest)); latest.status=status; latest.timestamp_ms=now;
  pending=0;count=0;sum=0;
}
void ADS_Probe_Init(const ADS_ProbeIO *bus,const ADS_ProbeConfig *c,uint32_t now)
{
  memset(&io,0,sizeof(io));memset(&latest,0,sizeof(latest));
  initialized=0;pending=0;count=0;sum=0;attempted=1;last_attempt=now;
  latest.status="ADC_NOT_INITIALIZED";
  if(!bus || !bus->start || !bus->read || !bus->stop || !config_valid(c)) return;
  io=*bus;config=*c;initialized=1;
}
void ADS_Probe_Poll(uint32_t now)
{
  if(!initialized) return;
  if(!pending) {
    if(attempted && (uint32_t)(now-last_attempt)<PROBE_PERIOD_MS) return;
    attempted=1;last_attempt=now;count=0;sum=0;
    if(!io.start(io.context)) { failed("ADC_READ_ERROR",now);return; }
    pending=1;conversion_started=now;return;
  }
  if((uint32_t)(now-conversion_started)>PROBE_TIMEOUT_MS) { failed("ADC_TIMEOUT",now);return; }
  uint16_t raw=0;int state=io.read(&raw,io.context);
  if(state<0) { failed("ADC_READ_ERROR",now);return; }
  if(!state) return;
  io.stop(io.context);
  ADS_ProbeMeasurement sample;
  if(!ADS_Probe_Convert(raw,&config,&sample)) {
    latest=sample;latest.timestamp_ms=now;pending=0;count=0;sum=0;return;
  }
  sum+=raw;count++;
  if(count<PROBE_AVERAGE_COUNT) {
    if(!io.start(io.context)) { failed("ADC_READ_ERROR",now);return; }
    conversion_started=now;return;
  }
  uint32_t sequence=latest.sequence+1;
  ADS_Probe_Convert((uint16_t)((sum+PROBE_AVERAGE_COUNT/2)/PROBE_AVERAGE_COUNT),&config,&latest);
  latest.sequence=sequence;latest.timestamp_ms=now;pending=0;
}
void ADS_Probe_Snapshot(ADS_ProbeMeasurement *out,uint32_t now)
{
  *out=latest;
  if(out->valid && (uint32_t)(now-out->timestamp_ms)>PROBE_STALE_MS) {
    out->valid=0;out->status="STALE";
  }
}
