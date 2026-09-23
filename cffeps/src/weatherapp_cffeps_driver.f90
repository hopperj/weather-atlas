program weatherapp_cffeps_driver
  use cffeps_mod
  use cffeps_fbp_mod, only: FMCcalc
  implicit none

  character(len=NB_CHAR_PATH) :: config_path, profile_path, output_path
  character(len=NB_CHAR_PATH) :: fire_weather_state_path, estimated_area_state_path
  integer(kind=4) :: fueltype_index, detection_julian, detection_hhmm, nsteps
  integer(kind=4) :: profile_unit, output_unit, config_unit, state_unit
  integer(kind=4) :: area_state_unit, ios
  integer(kind=4) :: step, level, year, month, day, hour, cmc_julian
  real(kind=4) :: lat, lon, ffmc, dmc, dc, bui, estarea_ha, elevation_m
  real(kind=4) :: percent_conifer, percent_dead_fir, grass_curing_percent
  real(kind=4) :: r_smoke, plume_top_m, cmc_utc, alpha_degrees
  real(kind=4) :: pending_flaming_t, pending_smoldering_t, pending_residual_t
  real(kind=4) :: mws(MAX_TIMESTEPS)
  type(feps_type) :: fire
  type(emissions_type) :: emissions
  type(met_type) :: met
  logical :: file_exists, use_fire_weather_states, use_estimated_area_states

  namelist /portable_cffeps/ profile_path, output_path, fueltype_index, &
       detection_julian, detection_hhmm, nsteps, lat, lon, ffmc, dmc, dc, &
       estarea_ha, elevation_m, percent_conifer, percent_dead_fir, &
       grass_curing_percent, cffeps_method, cffeps_fire_shape, &
       cffeps_fire_type, cffeps_radiation, cffeps_reset, cffeps_sinks, &
       cffeps_thstart, cffeps_thend, cffeps_timestep, cffeps_ldt, &
       alpha_degrees, cffeps_fbp_accel, fire_weather_state_path, &
       estimated_area_state_path

  call set_defaults()
  call get_command_argument(1, config_path)
  if (len_trim(config_path) == 0) call fail('usage: weatherapp-cffeps CONFIG.nml')
  inquire(file=trim(config_path), exist=file_exists)
  if (.not. file_exists) call fail('configuration file not found')

  open(newunit=config_unit, file=trim(config_path), status='old', action='read', iostat=ios)
  if (ios /= 0) call fail('unable to open configuration file')
  read(config_unit, nml=portable_cffeps, iostat=ios)
  close(config_unit)
  if (ios /= 0) call fail('invalid portable_cffeps namelist')
  call validate_inputs()
  use_fire_weather_states = len_trim(fire_weather_state_path) > 0
  if (use_fire_weather_states) then
     inquire(file=trim(fire_weather_state_path), exist=file_exists)
     if (.not. file_exists) call fail('fire-weather state file not found')
  end if
  use_estimated_area_states = len_trim(estimated_area_state_path) > 0
  if (use_estimated_area_states) then
     inquire(file=trim(estimated_area_state_path), exist=file_exists)
     if (.not. file_exists) call fail('estimated-area state file not found')
  end if

  cffeps_alpha = alpha_degrees * acos(-1.0) / 180.0
  call initialize_weights()
  call initialize_fire()

  open(newunit=profile_unit, file=trim(profile_path), status='old', action='read', iostat=ios)
  if (ios /= 0) call fail('unable to open meteorological profile file')
  if (use_fire_weather_states) then
     open(newunit=state_unit, file=trim(fire_weather_state_path), status='old', &
          action='read', iostat=ios)
     if (ios /= 0) call fail('unable to open fire-weather state file')
  end if
  if (use_estimated_area_states) then
     open(newunit=area_state_unit, file=trim(estimated_area_state_path), &
          status='old', action='read', iostat=ios)
     if (ios /= 0) call fail('unable to open estimated-area state file')
  end if
  open(newunit=output_unit, file=trim(output_path), status='replace', action='write', iostat=ios)
  if (ios /= 0) call fail('unable to open output file')
  write(output_unit, '(A)') 'step,year,month,day,hour,plume_top_m_agl,' // &
       'smoke_mixing_ratio_g_kg,fire_area_ha,flaming_fuel_t_h,' // &
       'smoldering_fuel_t_h,residual_fuel_t_h,total_consumed_fuel_t,' // &
       'pending_flaming_fuel_t,pending_smoldering_fuel_t,pending_residual_fuel_t'

  do step = 0, nsteps - 1
     read(profile_unit, *, iostat=ios) year, month, day, hour, met%hus, met%ws, met%Td
     if (ios /= 0) call fail('invalid or incomplete profile time record')
     do level = 1, MET_LEVELS
        read(profile_unit, *, iostat=ios) met%P(level), met%T(level), met%Z(level)
        if (ios /= 0) call fail('invalid or incomplete profile level record')
     end do
     if (use_fire_weather_states) then
        read(state_unit, *, iostat=ios) ffmc, dmc, dc
        if (ios /= 0) call fail('invalid or incomplete fire-weather state record')
        call set_fire_weather(ffmc, dmc, dc)
     end if
     if (use_estimated_area_states) then
        read(area_state_unit, *, iostat=ios) estarea_ha
        if (ios /= 0) call fail('invalid or incomplete estimated-area state record')
        if (estarea_ha < 0.0) call fail('hourly estimated area must be nonnegative')
        fire%estarea = estarea_ha
     end if
     call validate_profile()
     cmc_julian = jdays(month) + day
     if (mod(year, 4) == 0 .and. month > 2) cmc_julian = cmc_julian + 1
     cmc_utc = real(hour)
     if (step == 0) then
        cmcUTC0 = cmc_utc
        cmcDj0 = cmc_julian
     end if
     call cffeps_calc(fire, emissions, r_smoke, plume_top_m, met, mws, &
          cmc_julian, cmc_utc, step)
     ! CFFEPS stores these phase arrays in 10^-3 metric tonnes per hour
     ! (see the 1.0e-3 factor in EmissionsOverTime2), while totalemissions
     ! is reported in metric tonnes. Normalize the portable CSV contract to
     ! the labelled metric-tonnes-per-hour units at this boundary.
     pending_flaming_t = 1000.0 * sum(emissions%f(2:MAX_TIMESTEPS))
     pending_smoldering_t = 1000.0 * sum(emissions%s(2:MAX_TIMESTEPS))
     pending_residual_t = 1000.0 * sum(emissions%r(2:MAX_TIMESTEPS))
     write(output_unit, '(I0,4(",",I0),10(",",ES16.8))') step, year, month, day, hour, &
          plume_top_m, r_smoke, fire%area, 1000.0 * emissions%f(1), &
          1000.0 * emissions%s(1), 1000.0 * emissions%r(1), fire%totalemissions, &
          pending_flaming_t, pending_smoldering_t, pending_residual_t
  end do

  close(profile_unit)
  if (use_fire_weather_states) close(state_unit)
  if (use_estimated_area_states) close(area_state_unit)
  close(output_unit)

contains

  subroutine set_defaults()
    profile_path = 'profiles.txt'
    output_path = 'cffeps_portable_output.csv'
    fire_weather_state_path = ''
    estimated_area_state_path = ''
    fueltype_index = 2
    detection_julian = 183
    detection_hhmm = 0
    nsteps = 24
    lat = 45.0
    lon = -63.0
    ffmc = 90.0
    dmc = 40.0
    dc = 300.0
    estarea_ha = 100.0
    elevation_m = 100.0
    percent_conifer = 50.0
    percent_dead_fir = 35.0
    grass_curing_percent = 80.0
    cffeps_method = 'cmc'
    cffeps_fire_shape = 'weighted'
    cffeps_fire_type = 'dry'
    cffeps_timestep = 1.0
    alpha_degrees = 12.0
    cffeps_reset = -1.0
    cffeps_radiation = 0
    cffeps_sinks = .true.
    cffeps_thstart = 9.0
    cffeps_thend = 21.0
    cffeps_ldt = 0
    cffeps_fbp_accel = .false.
  end subroutine set_defaults

  subroutine initialize_weights()
    weight = (/0.015648395, 0.012470576, 0.010137905, 0.008443153, &
         0.004159725, 0.003641906, 0.004455177, 0.005716244, &
         0.017972534, 0.032938579, 0.043543306, 0.055667556, &
         0.065778522, 0.078207403, 0.090168462, 0.104189127, &
         0.101294339, 0.091901405, 0.072798822, 0.057406612, &
         0.044004006, 0.033647664, 0.025825035, 0.019983547/)
  end subroutine initialize_weights

  subroutine initialize_fire()
    fire%fueltype = fueltype_index
    fire%dtime = detection_hhmm
    fire%Dj = detection_julian
    fire%lat = lat
    fire%lon = lon
    call set_fire_weather(ffmc, dmc, dc)
    fire%fmc = FMCcalc(detection_julian, lat, lon, elevation_m)
    fire%percent_conifer = percent_conifer
    fire%percent_dead_fir = percent_dead_fir
    fire%curing = grass_curing_percent
    fire%area = 0.0
    fire%estarea = estarea_ha
    fire%Qo = 0.0
    fire%Qs = 0.0
    fire%totalemissions = 0.0
    emissions%f = 0.0
    emissions%s = 0.0
    emissions%r = 0.0
    mws = 0.0
  end subroutine initialize_fire

  subroutine set_fire_weather(state_ffmc, state_dmc, state_dc)
    real(kind=4), intent(in) :: state_ffmc, state_dmc, state_dc

    if (state_ffmc <= 0.0 .or. state_ffmc > 101.0) &
         call fail('fire-weather FFMC must be in (0, 101]')
    if (state_dmc <= 0.0 .or. state_dc <= 0.0) &
         call fail('fire-weather DMC and DC must be positive')
    if ((state_dmc * state_dc) == 0.0) then
       bui = 0.0
    else if (state_dmc <= (0.4 * state_dc)) then
       bui = 0.8 * state_dmc * state_dc / (state_dmc + 0.4 * state_dc)
    else
       bui = state_dmc - (1.0 - 0.8 * state_dc / &
            (state_dmc + 0.4 * state_dc)) * &
            (0.92 + ((0.0114 * state_dmc)**1.7))
    end if
    fire%ffmc = state_ffmc
    fire%dmc = state_dmc
    fire%dc = state_dc
    fire%bui = bui
  end subroutine set_fire_weather

  subroutine validate_inputs()
    if (nsteps < 1 .or. nsteps > MAX_TIMESTEPS) call fail('nsteps must be in [1, 24]')
    if (fueltype_index < 1 .or. fueltype_index > 18) call fail('fuel type must be burnable')
    if (ffmc <= 0.0 .or. ffmc > 101.0) call fail('ffmc must be in (0, 101]')
    if (dmc <= 0.0 .or. dc <= 0.0) call fail('dmc and dc must be positive')
    if (estarea_ha <= 0.0) call fail('estimated area must be positive')
    if (percent_conifer < 0.0 .or. percent_conifer > 100.0) &
         call fail('percent_conifer must be in [0, 100]')
    if (percent_dead_fir < 0.0 .or. percent_dead_fir > 100.0) &
         call fail('percent_dead_fir must be in [0, 100]')
    if (grass_curing_percent < 0.0 .or. grass_curing_percent > 100.0) &
         call fail('grass_curing_percent must be in [0, 100]')
    if (detection_julian < 1 .or. detection_julian > 366) call fail('invalid Julian day')
  end subroutine validate_inputs

  subroutine validate_profile()
    if (month < 1 .or. month > 12 .or. day < 1 .or. day > 31) &
         call fail('invalid profile date')
    if (hour < 0 .or. hour > 23) call fail('invalid profile hour')
    if (any(met%P <= 0.0) .or. any(met%T <= 0.0)) call fail('non-positive P or T')
    if (any(met%Z(2:) <= met%Z(:MET_LEVELS-1))) call fail('profile height must increase')
    if (any(met%P(2:) >= met%P(:MET_LEVELS-1))) call fail('profile pressure must decrease')
  end subroutine validate_profile

  subroutine fail(message)
    character(len=*), intent(in) :: message
    write(*, '(A)') 'ERROR: ' // trim(message)
    error stop 2
  end subroutine fail

end program weatherapp_cffeps_driver
