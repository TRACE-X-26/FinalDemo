/* ADC1/PA0 owner. CMSIS registers, as used by the existing timer driver.
 * HAL ADC files are absent from this checkout; no duplicate HAL initializer. */
#include "main.h"
#include "ads_board_config.h"
#include "ads_probe.h"
static uint32_t enabled_at;
static int start(void *context)
{
  (void)context;
  ADC1->SR=0;
  ADC1->CR2|=ADC_CR2_ADON;
  /* First acquisition is scheduled 100 ms after initialization/stabilization. */
  if(!(ADC1->CR2 & ADC_CR2_ADON)) return 0;
  ADC1->CR2|=ADC_CR2_SWSTART;return 1;
}
static int read_sample(uint16_t *raw,void *context)
{
  (void)context;
  if(ADC1->SR & ADC_SR_OVR) return -1;
  if(!(ADC1->SR & ADC_SR_EOC)) return 0;
  *raw=(uint16_t)ADC1->DR;return 1;
}
static void stop(void *context)
{ (void)context; ADC1->CR2 &= ~ADC_CR2_SWSTART;ADC1->SR=0; }
void ADS_Probe_BoardInit(void)
{
  __HAL_RCC_GPIOA_CLK_ENABLE();__HAL_RCC_ADC1_CLK_ENABLE();
  GPIO_InitTypeDef gpio={0};gpio.Pin=GPIO_PIN_0;gpio.Mode=GPIO_MODE_ANALOG;
  gpio.Pull=GPIO_NOPULL;HAL_GPIO_Init(GPIOA,&gpio);
  ADC1->CR2=0; ADC1->CR1=0; /* 12-bit; no scan or interrupts. */
  /* RM0368 section 11: PCLK2 / 4 = 21 MHz at the current 84 MHz clock.
   * 480 sampling cycles (~22.9 us) + 12 conversion cycles; long sampling
   * suits the divider's 7.5 kohm Thevenin resistance and 100 nF node. */
  ADC->CCR=(ADC->CCR & ~ADC_CCR_ADCPRE) | ADC_CCR_ADCPRE_0;
  ADC1->SMPR1=0;ADC1->SMPR2=ADC_SMPR2_SMP0;
  ADC1->SQR1=0;ADC1->SQR2=0;ADC1->SQR3=0; /* One conversion: channel 0. */
  ADC1->CR2=ADC_CR2_ADON;
  enabled_at=HAL_GetTick();
  ADS_ProbeConfig config={ADS_PROBE_REFERENCE_MV,ADS_PROBE_DIVIDER_NUM,
    ADS_PROBE_DIVIDER_DEN,ADS_PROBE_GAIN_PPM,ADS_PROBE_OFFSET_MV,12000U,ADS_PROBE_CALIBRATED};
  ADS_ProbeIO io={start,read_sample,stop,0};
  ADS_Probe_Init(&io,&config,enabled_at);
}
