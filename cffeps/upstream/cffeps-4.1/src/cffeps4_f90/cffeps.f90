 program cffeps

   use cffeps_mod,             only: cffeps_method, cffeps_fire_shape, &
                                     cffeps_fire_type, cffeps_sinks,   &
                                     cffeps_radiation, cffeps_reset,   &
                                     cffeps_thstart, cffeps_thend,     &
                                     cffeps_timestep, cffeps_ldt,      &
                                     cffeps_alpha, cffeps_fbp_accel,   &
                                     NB_CHAR_PATH
   use cffeps_speciations_mod, only: ngas, nvocs, npm, nb_fire_me_species
                              
   implicit none

   character(len=NB_CHAR_PATH) :: nmlfilename
   character(len=NB_CHAR_PATH) :: arg
   character(len=NB_CHAR_PATH) :: met_input_dir, hotspotfile, line
   integer(kind=4) :: nhotspots, nhrs, aqm_aerobins, online_init_hour

   integer(kind=4) :: funit, iun, read_status, i, ier
   logical(kind=4) :: file_exists

   namelist /cffeps_inputs_cfgs/ met_input_dir, hotspotfile, aqm_aerobins, &
                      cffeps_method, cffeps_fire_shape, cffeps_fire_type,  &
                      cffeps_radiation, cffeps_reset, cffeps_sinks,        &
                      cffeps_thstart, cffeps_thend, cffeps_timestep,       &
                      cffeps_ldt, cffeps_alpha, cffeps_fbp_accel,          &
                      online_init_hour 
                   
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

    ! It is important to set 'nb_fire_me_species' before cffeps_main
    ! is called, it is neeeded for defining a local variable in the routine
   nb_fire_me_species = ngas + nvocs + npm * max(2, (aqm_aerobins - 2))

   call cffeps_main(met_input_dir, hotspotfile, nhotspots, aqm_aerobins)
    
   stop

   contains

   subroutine cffeps_main(met_input_dir, hotspotfile, nhotspots, aqm_aerobins)
   use cffeps_mod,             only: feps_type, met_type, emissions_type, &
                                     cffeps_fueltypes, cmcUTC0, cmcDj0,   &
                                     jdays, NB_CHAR_PATH, max_timesteps
   use cffeps_speciations_mod, only: cffeps_emiss_speciations,   &
                                     me_species_gas, me_species_pm,   &
                                     me_species_voc, fire_me_species, &
                                     nb_fire_me_species, ngas, nvocs, npm
   use cffeps_fbp_mod,         only: FMCcalc
      
   implicit none

   integer(kind=4), intent(in)             :: nhotspots, aqm_aerobins
   character(len=NB_CHAR_PATH), intent(in) :: met_input_dir
   character(len=NB_CHAR_PATH), intent(in) :: hotspotfile

   type(FEPS_TYPE),      dimension(nhotspots) :: feps
   type(EMISSIONS_TYPE), dimension(nhotspots) :: emissions
   type(MET_TYPE),       dimension(nhotspots) :: met
  
   character(len=NB_CHAR_PATH)  :: hyb_filename, file_basename
   
   integer(kind=4)   :: cffeps_init  ! Function
   
   integer(kind=4)   :: istatus, ihs, ihr, istep, ij

   real(kind=4)      :: rsmoke, zplume, cmcUTC 
   integer(kind=4)   :: iyear, imonth, iday, ftime, cmcDj
   character(len=12) :: validity_datetime
   real(kind=4),    dimension(nhotspots, max_timesteps) :: mws
   real(kind=4),    dimension(nb_fire_me_species) :: mj_emis
   real(kind=4),    dimension(nhotspots)          :: elev
   integer(kind=4), dimension(nhotspots)          :: ddate
   
   integer(kind=4)   :: iunit, ounit, ounit2

   istatus = cffeps_init(hotspotfile, feps, ddate, nhotspots, aqm_aerobins)
   if (istatus < 0) then
      write(*, *) 'Error in initialising CFFEPS in cffeps_init '
      return
   end if

   ounit = 21
   open(unit=ounit, file='cffeps_output.csv', status='unknown')
   write(ounit, 25) 'LAT, LON, UTC, RSMK, ZPLM, ',  &
                    (fire_me_species(i), i = 1, nb_fire_me_species)
      
! Rewrite the hotspot file with updated (Qo, totalemissions, and Qs) parameters   
   ounit2 = 22
   open(unit=ounit2, file='cffeps_hotspots_out.csv', status='unknown')
   write(ounit2, *) 'lat, lon, ffmc, dmc, dc, fuel, estarea, ddate, dtime, ', &
                    & 'Qo, totalemissions, Qs'

   iunit = 17
   open(unit=iunit, file=(trim(met_input_dir)//'/met_filelist.txt'), &
        status='old', action='read')
        
   ihr = 0
   do
            
      read(iunit, *, end=95) file_basename
      hyb_filename  = trim(met_input_dir)//'/'// trim(file_basename)
      ihr = ihr + 1
! Read the MET fields from the FST file for the hour
      call readfst(feps, met, elev, nhotspots, hyb_filename, &
                   validity_datetime, istatus)
      if (istatus < 0) return
                   
   !/* Determine the hourly model (CMC) julian date */
      read(validity_datetime(1:4),'(i4.4)') iyear
      read(validity_datetime(5:6),'(i2.2)') imonth
      read(validity_datetime(7:8),'(i2.2)') iday
      cmcDj = jdays(imonth) + iday
      if (mod(iyear, 4) == 0 .and. imonth >2) &
         cmcDj = cmcDj + 1
      read(validity_datetime(9:12), '(i4.4)') ftime  !HHMM
      !// UTC time of forecast hour
      cmcUTC = real(int(ftime / 100)) + real(mod(ftime, 100)) / 60.0
      if (ihr == 1) then
         cmcUTC0 = cmcUTC
         cmcDj0  = cmcDj
      end if
      
      istep = ihr - 1
      
      do ihs = 1, nhotspots
         
         if (ihr == 1) then
            emissions(ihs)%f = 0.0
            emissions(ihs)%s = 0.0
            emissions(ihs)%r = 0.0
            
            mws(ihs, :) = 0.0
            
            feps(ihs)%fmc = FMCcalc(feps(ihs)%dj, feps(ihs)%lat, &
                                    feps(ihs)%lon, elev(ihs))
         end if
         
         call cffeps_calc(feps(ihs), emissions(ihs), rsmoke, zplume, &
                          met(ihs), mws(ihs, :), cmcDj, cmcUTC, istep)

!        Estimate the mass of model species emiited from the fire
         call cffeps_emiss_speciations(emissions(ihs), mj_emis, &
                                       aqm_aerobins)
            
         write(ounit, 35) feps(ihs)%lat, feps(ihs)%lon, validity_datetime, &
                          rsmoke, zplume, (mj_emis(i), i = 1, nb_fire_me_species)
               
         if (ihr == online_init_hour) then
            write(ounit2, 45) feps(ihs)%lat, feps(ihs)%lon, feps(ihs)%ffmc,   &
                              feps(ihs)%dmc, feps(ihs)%dc,                    &
                              cffeps_fueltypes(feps(ihs)%fueltype),           &
                              feps(ihs)%estarea, ddate(ihs), feps(ihs)%dtime, &
                              feps(ihs)%Qo, feps(ihs)%totalemissions,         &
                              (feps(ihs)%Qs(ij), ij = 1, max_timesteps)
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
 35 format(F6.3, ',', F9.3, ',', A12, ',', E15.7, ',', F9.3, 90(',', E15.7))
 45 format(F6.3, 4(1X, F8.3), 1X, A8, 1X, F8.3, 1X, I8, 1X, I4, 26(1X, E15.7))
 
   return
   end subroutine cffeps_main
      
 end program cffeps
