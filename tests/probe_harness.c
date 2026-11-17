#include "ads_probe.h"
#include "ads_protocol.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static uint32_t now;
static uint16_t raw=1551;
static int state=1,start_ok=1;
static ADS_ProbeConfig config={3300,4,1,1000000,0,12000,0};
static int start(void *ctx) { (void)ctx;return start_ok; }
static int read_adc(uint16_t *out,void *ctx) { (void)ctx;*out=raw;return state; }
static void stop(void *ctx) { (void)ctx; }
static ADS_ProbeIO io={start,read_adc,stop,0};
static void burst(uint32_t begin)
{ ADS_Probe_Poll(begin);for(unsigned i=1;i<=4;i++) ADS_Probe_Poll(begin+i); }
static void checks(void)
{
  ADS_ProbeMeasurement p;
  uint16_t counts[]={0,931,1551,2792,3723};
  int32_t volts[]={0,3000,5000,9000,12000};
  for(unsigned i=0;i<5;i++) {
    assert(ADS_Probe_Convert(counts[i],&config,&p));
    assert(abs(p.voltage_mv-volts[i])<=2);assert(!p.calibrated);
  }
  assert(!ADS_Probe_Convert(4080,&config,&p));assert(!strcmp(p.status,"OUT_OF_RANGE"));
  assert(p.raw_valid && !p.valid);
  assert(!ADS_Probe_Convert(65535,&config,&p));assert(!p.raw_valid);
  ADS_ProbeConfig calibrated=config;calibrated.reference_mv=3290;
  calibrated.divider_num=401;calibrated.divider_den=100;
  assert(ADS_Probe_Convert(1551,&calibrated,&p));assert(p.voltage_mv>4990);
  calibrated.divider_den=0;assert(!ADS_Probe_Convert(1551,&calibrated,&p));
  calibrated=config;calibrated.gain_ppm=1010000;calibrated.offset_mv=10;calibrated.calibrated=1;
  assert(ADS_Probe_Convert(1551,&calibrated,&p));assert(p.voltage_mv>5040 && p.calibrated);
  ADS_Probe_Init(0,&config,0);ADS_Probe_Snapshot(&p,0);
  assert(!p.valid && !strcmp(p.status,"ADC_NOT_INITIALIZED"));
  ADS_Probe_Init(&io,&config,0);burst(100);ADS_Probe_Snapshot(&p,104);
  assert(p.valid && p.raw_adc==1551 && p.sequence==1);
  ADS_Probe_Snapshot(&p,605);assert(!p.valid && !strcmp(p.status,"STALE"));
  state=0;ADS_Probe_Poll(200);ADS_Probe_Poll(221);ADS_Probe_Snapshot(&p,221);
  assert(!p.valid && !p.raw_valid && !strcmp(p.status,"ADC_TIMEOUT"));
  state=-1;ADS_Probe_Poll(300);ADS_Probe_Poll(301);ADS_Probe_Snapshot(&p,301);
  assert(!p.valid && !strcmp(p.status,"ADC_READ_ERROR"));
  state=1;raw=4095;burst(400);ADS_Probe_Snapshot(&p,404);
  assert(!p.valid && p.raw_adc==4095 && !strcmp(p.status,"OUT_OF_RANGE"));
  raw=0;burst(500);ADS_Probe_Snapshot(&p,504);assert(p.valid && p.voltage_mv==0);
  start_ok=0;ADS_Probe_Poll(600);ADS_Probe_Snapshot(&p,600);assert(!p.valid);
  start_ok=1;raw=1551;ADS_Probe_Init(&io,&config,0xfffffff0U);
  burst(84);ADS_Probe_Snapshot(&p,88);assert(p.valid); /* uint32 wrap */
}
static uint32_t tick(void *ctx) { (void)ctx;return now; }
static int transmit(const uint8_t *b,size_t n,void *ctx)
{ (void)ctx;return fwrite(b,1,n,stdout)==n?0:-1; }
static void probe(ADS_ProbeMeasurement *out,void *ctx)
{ (void)ctx;ADS_Probe_Snapshot(out,now); }
static void acquire(ADS_Sample out[5],void *ctx)
{ (void)ctx;memset(out,0,5*sizeof(*out)); }
static void branches(ADS_ElectricalBranch out[2],void *ctx)
{
  (void)ctx;memset(out,0,2*sizeof(*out));
  for(unsigned i=0;i<2;i++) {
    out[i].address=(uint8_t)(0x40+i);out[i].connected=1;out[i].configured=1;
    out[i].status="CONNECTED";out[i].completed_ms=now;
    for(unsigned j=0;j<3;j++) out[i].samples[j]=(ADS_Sample){(i?5000:12000),now,1};
  }
}
int main(int argc,char **argv)
{
  if(argc==1) {checks();return 0;}
  raw=(uint16_t)atoi(argv[1]);ADS_Probe_Init(&io,&config,0);burst(100);now=104;
  if(argc>2) now=1000;
  ADS_Protocol p;ADS_Protocol_Init(&p,transmit,tick,0);p.require_crc=1;
  ADS_Protocol_SetProbe(&p,probe);ADS_Protocol_SetBranches(&p,branches);
  ADS_Protocol_SetHardwareCallbacks(&p,acquire,0);
  int ch;while((ch=getchar())!=EOF) ADS_Protocol_ProcessByte(&p,(uint8_t)ch);
  return 0;
}
