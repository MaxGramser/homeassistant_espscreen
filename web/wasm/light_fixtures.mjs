// Shared native light-card fixtures, also used for round-display coverage.
export const both = { entity: 'light.desk', name: 'Desk', state: 'on', slot: 0, o: {},
  a: { brightness: 128, color_mode: 'hs', hs_color: [30, 60], color_temp_kelvin: 3000, min_color_temp_kelvin: 2000,
       max_color_temp_kelvin: 6500, supported_color_modes: ['color_temp', 'hs'] } };
export const warm = { ...both, entity: 'light.hall', name: 'Hall', slot: 1, a: { ...both.a, supported_color_modes: ['color_temp'], color_mode: 'color_temp' } };
