 program mach_cffeps

   use mach_cffeps_mod,             only: cffeps_method, cffeps_fire_shape, &
                                          cffeps_fire_type, cffeps_sinks,   &
                                          cffeps_radiation, cffeps_reset,   &
                                          cffeps_thstart, cffeps_thend,     &
                                          cffeps_timestep, cffeps_ldt,      &
                                          cffeps_alpha, cffeps_fbp_accel,   &
                                          cffeps_fc_method, cffeps_diurnal, &
                                          cffeps_buieff,                    &
                                          NB_CHAR_PATH, MAX_TIMESTEPS
   use mach_cffeps_speciations_mod, only: ngas, nvocs, npm, nb_fire_me_species

   implicit none

   character(len=NB_CHAR_PATH) :: nmlfilename
   character(len=NB_CHAR_PATH) :: arg
   character(len=NB_CHAR_PATH) :: met_input_dir, hotspotfile, line
   integer(kind=4) :: nhotspots, aqm_aerobins, online_init_hour, max_hours

   integer(kind=4) :: funit, iun, read_status, i, ier
   logical(kind=4) :: file_exists

   namelist /cffeps_inputs_cfgs/ met_input_dir, hotspotfile, aqm_aerobins, &
                      cffeps_method, cffeps_fire_shape, cffeps_fire_type,  &
                      cffeps_radiation, cffeps_reset, cffeps_sinks,        &
                      cffeps_thstart, cffeps_thend, cffeps_timestep,       &
                      cffeps_ldt, cffeps_alpha, cffeps_fbp_accel,          &
                      cffeps_fc_method, cffeps_diurnal, cffeps_buieff,     &
                      online_init_hour, max_hours

   i = 1
   call get_command_argument(i, arg)
   inquire(FILE = arg, EXIST = file_exists)

   if (file_exists) then
      nmlfilename = trim(arg)
   else
      write(*, *) trim(arg)// ": file not found"
      stop
   end if

! Read the input namelist and initialize CFFEPS

!/* These are the default CFFEPS values */
   cffeps_method = "cmc"              !/* FIREWORK calculations */
   hotspotfile = "input.csv"          !/* name of Peter's hotspot file name */
   met_input_dir = "input/meteo_dir/" !/* Path to input Meteorological data (FST files) */
   aqm_aerobins  = 2                  !/* AQ model aerosol bins
   online_init_hour = 24              ! Hour to print output for cffeps_online initiazation
   max_hours = 24                     ! Maximum number of hours for future distribution of fire energy

   cffeps_fire_shape = "weighted"
   cffeps_fire_type = "average"   !/* type of upper air profile method used (average lapse rate, dry, wet) */
   cffeps_timestep = 1.00     ! /* timestep for modelling black body radiation loss (no timestep means no BB radiation) */
   cffeps_alpha = 12.0        ! /* entrainment half-angle (0. = no entrainment) */
   cffeps_reset = -1.0        ! /* reset time of smoke plume calculations [decimal hours LST] (off if < 0) */
   cffeps_radiation = 0       ! /* method of calculating radiation term: < 0 Byram's 1200/8600; =0 A_wall/A_top; > 0  value as % of Qfire */
   cffeps_sinks = .true.      ! /* include heat sinks in calculation >0 = yes */
   cffeps_thstart = 9.0       ! /* time to start (exclusive) top-hat fire growth [decimal hours LST] */
   cffeps_thend = 21.0        ! /* time to end (inclusive) top-hat fire growth [decimal hours LST] */
   cffeps_ldt = 0             ! /* Local Daylight Time 1= one hour time offset */
   cffeps_fbp_accel = .false. ! // false, no acceleration
   cffeps_buieff = .false.    ! /* Turn off BUI effect by defa
   cffeps_fc_method = 1       ! Fuel consumption method (1 = default FBP)
   cffeps_diurnal = "OFF"     ! Equilibrium Moisture Content -- 2020-06-04
!   cffeps_diurnal = "BDL"     ! BDL tabular hourly FFMC -- 2020-06-04

   iun = 15
   open(unit = iun, file = trim(nmlfilename), status = 'old', iostat = ier)
   if (ier == 0) then
      rewind(iun)
      read (iun, nml = cffeps_inputs_cfgs, iostat = read_status)
      if (read_status > 0) then
         write(*, *) 'Error in reading namelist cffeps_inputs_cfgs from ', &
                     nmlfilename
         backspace(iun)
         read(iun, '(A)') line
         write(*, *) 'Invalid line in cffeps_inputs_cfgs namelist ', trim(line)
         write(*, *) ' Read status = ', read_status
         stop
      else if (read_status < 0) then
         write(*, *) 'No cffeps_inputs_cfgs found in input file --> ABORT ALL!!'
         close(unit = iun)
         stop
      end if
   else
      write(*, *)'Error opening input file - ', nmlfilename
      stop
   end if
   close(unit = iun)

   funit = 16
   open(unit=funit, file=trim(hotspotfile), status='old', action='read')

      ! First determine the number of fire hotspots
   read(funit, *)   ! The header
   nhotspots = 0
   do
     read(funit, *, end=85) line
     nhotspots = nhotspots + 1
   end do

 85 close(funit)

! Set MAX_TIMESTEPS
   MAX_TIMESTEPS = nint(max_hours / cffeps_timestep)

    ! It is important to set 'nb_fire_me_species' before cffeps_main
    ! is called, it is neeeded for defining a local variable in the routine
   nb_fire_me_species = ngas + nvocs + npm * max(2, (aqm_aerobins - 2))

   call mach_cffeps_main(met_input_dir, hotspotfile, nhotspots, aqm_aerobins)

   stop

   contains

   subroutine mach_cffeps_main(met_input_dir, hotspotfile, nhotspots, aqm_aerobins)
   use mach_cffeps_mod,             only: feps_type, met_type, emissions_type, &
                                          cffeps_fueltypes, max_timesteps,     &
                                          jdays, NB_CHAR_PATH
   use mach_cffeps_speciations_mod, only: cffeps_emiss_speciations,   &
                                          me_species_gas, me_species_pm,   &
                                          me_species_voc, fire_me_species, &
                                          nb_fire_me_species, ngas, nvocs, npm
   use mach_readfst_mod,            only: mach_readfst

   implicit none

   integer(kind=4), intent(in)             :: nhotspots, aqm_aerobins
   character(len=NB_CHAR_PATH), intent(in) :: met_input_dir
   character(len=NB_CHAR_PATH), intent(in) :: hotspotfile

   type(FEPS_TYPE),      dimension(nhotspots) :: feps
   type(EMISSIONS_TYPE), dimension(nhotspots) :: emissions
   type(MET_TYPE),       dimension(nhotspots) :: met

   character(len=NB_CHAR_PATH)  :: hyb_filename, file_basename

   integer(kind=4)   :: mach_cffeps_init  ! Function

   integer(kind=4)   :: istatus, ihs, ihr, istep, ij

   real(kind=4)      :: rsmoke, zplume, cmcUTC
   integer(kind=4)   :: iyear, imonth, iday, ihour, iminute, cmcDj
   character(len=12) :: validity_datetime
   real(kind=4),    dimension(nhotspots, max_timesteps) :: mws
   real(kind=4),    dimension(nhotspots, 24) :: ross
   real(kind=4),    dimension(max_timesteps) :: mws_ihs
   real(kind=4),    dimension(24) :: ross_ihs
   real(kind=4),    dimension(nb_fire_me_species) :: mj_emis
   logical(kind=4), dimension(nhotspots)          :: valid_hotspots

   integer(kind=4)   :: iunit, ounit, ounit2

   iunit = 17
   open(unit=iunit, file=(trim(met_input_dir)//'/met_filelist.txt'), &
        status='old', action='read')
   read(iunit, *, end=95) file_basename
   hyb_filename  = trim(met_input_dir)//'/'// trim(file_basename)

   istatus = mach_cffeps_init(hotspotfile, feps, nhotspots, aqm_aerobins)
   if (istatus <= 0) then
      if (istatus == 0) then
         open(unit=21, file='cffeps_no_hotspot.txt', status='new')
         write(21, *) 'NO FIRE HOTSPOTS WITHIN THE PILOTING MET. FIELD DOMAIN'
      else
         write(*, *) 'Error in initialising CFFEPS in mach_cffeps_init '
      end if
      return
   end if

   ihr = 0
   rewind(iunit)
   do

      read(iunit, *, end=95) file_basename
      hyb_filename  = trim(met_input_dir)//'/'// trim(file_basename)
      ihr = ihr + 1
! Read the MET fields from the FST file for the hour
      call mach_readfst(feps%lat, feps%lon, nhotspots, hyb_filename, met, &
                        validity_datetime, ihr, valid_hotspots, istatus)
      if (istatus < 0) then
         write(0,*)'Error status returned from call to mach_readfst'
         return
      end if

   !/* Determine the hourly model (CMC) julian date */
      read(validity_datetime(1:4),'(i4.4)') iyear
      read(validity_datetime(5:6),'(i2.2)') imonth
      read(validity_datetime(7:8),'(i2.2)') iday
      cmcDj = jdays(imonth) + iday
      if (mod(iyear, 4) == 0 .and. imonth >2) &
         cmcDj = cmcDj + 1
      read(validity_datetime(9:10),  '(i2.2)') ihour
      read(validity_datetime(11:12), '(i2.2)') iminute
      !// UTC time of forecast hour
      cmcUTC = real(ihour) + real(iminute) / 60.0
      if (ihr == 1) then
!
         ounit = 21
         open(unit=ounit, file='cffeps_output.csv', status='unknown')
         write(ounit, 25) 'LAT, LON, UTC, RSMK, ZPLM, ',  &
                         (fire_me_species(i), i = 1, nb_fire_me_species)

! Rewrite the hotspot file with updated (Qo, totalemissions, and Qs) parameters
         ounit2 = 22
         open(unit=ounit2, file='cffeps_hotspots_out.csv', status='unknown')
         write(ounit2, *) 'lat, lon, ffmc, dmc, dc, fuel, estarea, dtime, djdate, ', &
                          & 'Qo, totalemissions, Qs'

      end if

      istep = ihr - 1

      do ihs = 1, nhotspots

         if (.not. valid_hotspots(ihs)) cycle

         if (ihr == 1) then
            allocate(emissions(ihs)%f(max_timesteps))
            allocate(emissions(ihs)%s(max_timesteps))
            allocate(emissions(ihs)%r(max_timesteps))
            emissions(ihs)%f = 0.0
            emissions(ihs)%s = 0.0
            emissions(ihs)%r = 0.0

            allocate(feps(ihs)%qs(max_timesteps))
            feps(ihs)%qs = 0.0

            mws(ihs, :)  = 0.0
            ross(ihs, :) = 0.0

         end if

         mws_ihs  = mws(ihs, :)
         ross_ihs = ross(ihs, :)
         call mach_cffeps_calc(feps(ihs), emissions(ihs), rsmoke, zplume, met(ihs), &
                               mws_ihs, ross_ihs, cmcDj, cmcUTC, ihour, istep)
         mws(ihs, :)  = mws_ihs
         ross(ihs, :) = ross_ihs

!        Estimate the mass of model species emiited from the fire
         call cffeps_emiss_speciations(emissions(ihs), mj_emis, aqm_aerobins)

         write(ounit, 35) feps(ihs)%lat, feps(ihs)%lon, validity_datetime, &
                          rsmoke, zplume, (mj_emis(i), i = 1, nb_fire_me_species)

         if (ihr == online_init_hour) then
            write(ounit2, 45) feps(ihs)%lat, feps(ihs)%lon, feps(ihs)%dtime, real(feps(ihs)%dj), &
                              cffeps_fueltypes(feps(ihs)%fueltype), feps(ihs)%estarea,      &
                              feps(ihs)%area, feps(ihs)%ffmc, &
                              feps(ihs)%fmc, feps(ihs)%dmc, feps(ihs)%dc, feps(ihs)%curing, &
                              feps(ihs)%gs, feps(ihs)%aspect, feps(ihs)%pc, feps(ihs)%pdf,  &
                              feps(ihs)%cbh, feps(ihs)%gfl, feps(ihs)%lfl, feps(ihs)%dfl,   &
                              feps(ihs)%sfl, feps(ihs)%cfl, feps(ihs)%ffl, feps(ihs)%wfl,   &
                              feps(ihs)%sh, feps(ihs)%sd, feps(ihs)%Qo, feps(ihs)%totalemissions, &
                              rsmoke, zplume, (feps(ihs)%qs(ij), ij = 1, 24), (mws_ihs(ij), ij = 1, 24), &
                              (emissions(ihs)%f(ij), emissions(ihs)%s(ij), emissions(ihs)%r(ij), ij = 1, 24)
         end if
      end do

   end do
!
 95  close(iunit)
!
   close(ounit)
!
   close (ounit2)
!
 25 format(A25, 90(', ', A4))
 35 format(F7.4, ',', F10.4, ',', A12, ',', E15.7, ',', F9.3, 90(',', E15.7))
 45 format(4(F10.4, 1X), A8, 21(1X, F10.4), 124(1X, E15.7))

   return
   end subroutine mach_cffeps_main

 end program mach_cffeps
