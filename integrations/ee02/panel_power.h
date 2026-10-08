#pragma once
#include "driver/gpio.h"
#include "esp_sleep.h"
#include "esp_random.h"

// EE02 GPIO43 drives the panel load switch and has no external pull-down.
inline void release_panel_power_hold() {
  gpio_set_direction(GPIO_NUM_43, GPIO_MODE_OUTPUT);
  gpio_set_level(GPIO_NUM_43, 0);
  gpio_hold_dis(GPIO_NUM_43);
  gpio_deep_sleep_hold_dis();
}

inline void hold_panel_power_off() {
  gpio_set_level(GPIO_NUM_43, 0);
  gpio_hold_en(GPIO_NUM_43);
  gpio_deep_sleep_hold_en();
}
