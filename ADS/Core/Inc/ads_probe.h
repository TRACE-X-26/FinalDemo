#ifndef ADS_PROBE_H
#define ADS_PROBE_H
#include <stdint.h>
typedef struct {
  uint32_t reference_mv, divider_num, divider_den, gain_ppm;
  int32_t offset_mv;
  uint32_t max_voltage_mv;
  uint8_t calibrated;
} ADS_ProbeConfig;
typedef struct {
  uint16_t raw_adc;
  uint8_t raw_valid, valid, calibrated;
  int32_t voltage_mv;
  uint32_t adc_pin_uv, timestamp_ms, sequence;
  const char *status;
} ADS_ProbeMeasurement;
typedef struct {
  int (*start)(void *);
  int (*read)(uint16_t *,void *); /* 0 pending; 1 complete; -1 error */
  void (*stop)(void *);
  void *context;
} ADS_ProbeIO;
void ADS_Probe_Init(const ADS_ProbeIO *,const ADS_ProbeConfig *,uint32_t now);
void ADS_Probe_Poll(uint32_t now);
void ADS_Probe_Snapshot(ADS_ProbeMeasurement *,uint32_t now);
int ADS_Probe_Convert(uint16_t,const ADS_ProbeConfig *,ADS_ProbeMeasurement *);
void ADS_Probe_BoardInit(void);
#endif
