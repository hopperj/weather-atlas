!---------------------------------- LICENCE BEGIN -------------------------------
! GEM-MACH - Atmospheric chemistry library for the GEM numerical atmospheric model
! Copyright (C) 2007-2018 - Air Quality Research Division &
!                           National Prediction Operations division
!                           Environnement Canada
! This library is free software; you can redistribute it and/or
! modify it under the terms of the GNU Lesser General Public
! License as published by the Free Software Foundation; either
! version 2.1 of the License, or (at your option) any later version.
!
! This library is distributed in the hope that it will be useful,
! but WITHOUT ANY WARRANTY; without even the implied warranty of
! MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
! Lesser General Public License for more details.
!
! You should have received a copy of the GNU Lesser General Public
! License along with this library; if not, write to the Free Software
! Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
!---------------------------------- LICENCE END ---------------------------------

!============================================================================!
!         Environnement Canada         |        Environment Canada           !
!                                      |                                     !
! - Service meteorologique du Canada   | - Meteorological Service of Canada  !
! - Direction generale des sciences    | - Science and Technology Branch     !
!   et de la technologie               |                                     !
!============================================================================!
!                            http://www.ec.gc.ca                             !
!============================================================================!
!
! Projet / Project : GEM-MACH
! Fichier / File   : cffeps_init.ftn90
! Creation         : A. Akingunola, J. Chen, P. Makar, and Kerry Anderson 
!                     - Fall 2018
! Description      : Read the input hotspotfile and initialize CFFEPS
!
!
integer function cffeps_init(hotspotfile, feps_inp, ddate_o, nhotspots, &
                             aqm_aerobins)

   use cffeps_mod
   use cffeps_speciations_mod, only: me_species_gas, me_species_pm,   &
                                     me_species_voc, fire_me_species, &
                                     nb_fire_me_species, ngas, nvocs, npm

   implicit none

   integer(kind=4),             intent(in)    :: nhotspots, aqm_aerobins
   character(len=NB_CHAR_PATH), intent(in)    :: hotspotfile
   type(feps_type), dimension(nhotspots), intent(out) :: feps_inp
   integer(kind=4), dimension(nhotspots), intent(out) :: ddate_o

   integer(kind=4)  :: ddate, imonth, iyear, iday
   integer(kind=4)  :: funit, i
   real(kind=4)     :: dt
   character(len=8) :: fuel

   integer(kind=4) :: ifuel    ! Fueltype
   integer(kind=4) :: dtime    ! detection time of fire HHMM (time all values are assumed to be collected)
   integer(kind=4) :: dj       ! detection Julian Day
   real(kind=4)    :: lat      ! Latitude [decimal degrees]
   real(kind=4)    :: lon      ! Longitude [decimal degrees]
   real(kind=4)    :: ffmc     ! FFMC
   real(kind=4)    :: dmc      ! Duff Moisture Code
   real(kind=4)    :: dc       ! Drought Code
   real(kind=4)    :: bui      ! BUI
   real(kind=4)    :: estarea  ! estimated fire size at time of detection
   
   real(kind=4), parameter :: conva = 180.0 / acos(-1.0)
   character(len=1) :: zbin
   integer(kind=4)  :: nsp, nbin, sn, emis_nb_bins
   
   cffeps_init = -1

! Initialize weight; weight(17) adjusted to make the total = 1
   weight =  (/0.015648395, 0.012470576, 0.010137905, 0.008443153, &
               0.004159725, 0.003641906, 0.004455177, 0.005716244, &
               0.017972534, 0.032938579, 0.043543306, 0.055667556, &
               0.065778522, 0.078207403, 0.090168462, 0.104189127, &
               0.101294339, 0.091901405, 0.072798822, 0.057406612, &
               0.044004006, 0.033647664, 0.025825035, 0.019983547/)
                        
      
    cffeps_alpha = cffeps_alpha / conva     !/* convert to radians */

    select case (trim(cffeps_method))
       case ("Alberta", "AB")
         cffeps_method = "AB"
       case ("cmc", "firework")
         cffeps_method = "cmc"
       case ("bigfoot", "bf")
         cffeps_method = "bigfoot"
       case ("standard", "icao")
         cffeps_method = "icao"
    end select

    select case (trim(cffeps_fire_shape))
       case ("line", "wedge", "perimeter")
         cffeps_fire_shape = "line"
       case ("tophat", "persistence")
         cffeps_fire_shape = "tophat"
    end select

    if (trim(cffeps_fire_type) == "piecewise") cffeps_fire_type = "dry"

    if (cffeps_thstart > 24. .or. cffeps_thend > 24.) then
       cffeps_thstart = (int(cffeps_thstart) / 100) + (mod(int(cffeps_thstart), 100) / 60.)
       cffeps_thend = (int(cffeps_thend) / 100) + (mod(int(cffeps_thend), 100) / 60.)
    end if

    if (cffeps_thstart >= cffeps_thend) then
       write(*,*)"Warning: Top-hat start ", cffeps_thstart, " >= Top-hat end ", cffeps_thend
       cffeps_thstart = 9.0    !/* time to start (exclusive) top-hat fire growth [decimal hours LST] */
       cffeps_thend = 21.0     !/* time to end (inclusive) top-hat fire growth [decimal hours LST] */
    end if
    
    if (cffeps_reset > 24.) &
       cffeps_reset = (int(cffeps_reset) / 100) + (mod(int(cffeps_reset), 100) / 60.)

    if (cffeps_ldt == 100 .or. cffeps_ldt == 1) then
       cffeps_ldt = 1
    else
       cffeps_ldt = 0
    end if
!
!  Assign weight array values to top-hat approach (if used)
    if (trim(cffeps_fire_shape) == "top-hat") then
       do i = 0, 23
          if (i >= floor(cffeps_thstart) .and. i < ceiling(cffeps_thend)) then
             if ((cffeps_thend - cffeps_thstart) < 1.0) then
                dt = cffeps_thend - cffeps_thstart
             else if ((i < cffeps_thstart) .and. &
                     (cffeps_thstart - real(i)) < 1.0) then
                 dt = real(i) + 1.0 - cffeps_thstart
             else if (cffeps_thend - real(i) < 1.0) then
                 dt = cffeps_thend - real(i)
             else
                 dt = 1.0
             end if
             weight(i + 1) = dt / (cffeps_thend - cffeps_thstart)
          else
             weight(i + 1) = 0.0
          end if
       end do
    end if
!
! NOTE: The FBP Accel should be hotspot dependent, but it is fixed for now.
    if (cffeps_fire_shape(1:4) == "line") then
       cffeps_fbp_accel = .false.
    end if 
!
!   ! Now read the hotspots' data
!*** Make reading the hotspot input as similar as possible to the
!*** way it is done for the online (GEM-MACH integrated) version
    funit = 11
    open(unit=funit, file=trim(hotspotfile), status='old', action='read')
    
    read(funit, *) ! First read the header
    do i = 1, nhotspots
       read(funit, 30) lat, lon, ffmc, dmc, dc, fuel, estarea, ddate, dtime
                            
!/* Determine julian date */
       iyear = int(ddate / 10000)
       imonth = int((ddate - 10000 * iyear) / 100)
       iday = ddate - 10000 * iyear - 100 * imonth
       dj = jdays(imonth) + iday
       if (iyear > 0 .and. mod(iyear, 4) == 0 .and. imonth >2) &
          dj = dj + 1
!
! Reassign fuel type (if required). 
!      If there is no matching fuel type, set to NF. */
!      forall(j = 1:fuel_size) fuel(j:j) = clib_toupper(fuel(j:j))
       fuel = adjustl(fuel)
       if (fuel(1:2) == "C1") then
          ifuel = 1
       else if (fuel(1:2) == "C2") then
          ifuel = 2
       else if (fuel(1:2) == "C3") then
          ifuel = 3
       else if (fuel(1:2) == "C4") then
          ifuel = 4
       else if (fuel(1:2) == "C5") then
          ifuel = 5
       else if (fuel(1:2) == "C6") then
          ifuel = 6
       else if (fuel(1:2) == "C7") then
          ifuel = 7
       else if (fuel(1:2) == "D2" .or. fuel(1:2) == "D1") then
          ifuel = 8
       else if (fuel(1:2) == "M1") then
          ifuel = 10
       else if (fuel(1:2) == "M2") then
          ifuel = 11
       else if (fuel(1:2) == "M3") then
          ifuel = 12
       else if (fuel(1:2) == "M4") then
          ifuel = 13
       else if (fuel(1:2) == "S1") then
          ifuel = 14
       else if (fuel(1:2) == "S2") then
          ifuel = 15
       else if (fuel(1:2) == "S3") then
          ifuel = 16
       else if (trim(fuel) == "CROPLAND" .or. trim(fuel) == "LOW_VEG" .or. &
                trim(fuel) == "O1A" .or. trim(fuel) == "O1a") then
          ifuel = 17
       else if (fuel(1:2) == "O1") then
          ifuel = 18
       else if (fuel(1:2) == "WA") then
          ifuel = 19
       else 
        ! ("URBAN", "BOG", "WATER", "NON-FUEL") and anything else is undefined
          ifuel = 20
       end if

! FBP (Fire Behavior Prediction System) checks     
       if (ffmc < 0.0 .or. ffmc > 101.0) &
          ffmc = 0.0
!/* Calculate the BUI value from DMC and DC values.  Determine whether the BUI
!      effect is being used. (Excerpt of BUICalc in Fbp sub-module) */
             !// updated fix 2015-11-09 KRA
       if ((dmc * dc) == 0.0) then
          bui = 0.0
       else
          if (dmc <= (0.4 * dc)) then      ! /* 27a */
             bui = 0.8 * dmc * dc / (dmc + 0.4 * dc)
          else                             ! /* 27b */
             bui = dmc - (1.0 - 0.8 * dc / (dmc + 0.4 * dc)) *     &
                   (0.92 + ((0.0114 * dmc)**1.7))
          end if
          if (bui < 0.0 .or. bui > 1000.0) &
             bui = 0.0    !/* This turns off BUI effect */
       end if

       feps_inp(i)%fueltype = ifuel
       feps_inp(i)%dtime    = dtime
       feps_inp(i)%dj       = dj
       
       feps_inp(i)%lat      = lat
       feps_inp(i)%lon      = lon
       feps_inp(i)%ffmc     = ffmc
       feps_inp(i)%dmc      = dmc
       feps_inp(i)%dc       = dc
       feps_inp(i)%bui      = bui
       feps_inp(i)%estarea  = estarea
!
! Initialize other feps_type components that are not read/computed from input
       feps_inp(i)%fmc      = -1.0
       feps_inp(i)%area     = 0.0
       feps_inp(i)%Qo       = 0.0
       feps_inp(i)%Qs       = 0.0
       feps_inp(i)%totalemissions = 0.0     
       
       ddate_o(i)           = ddate
    end do

    close(funit)
 30 format(F6.3, 4(1X, F8.3), 1X, A8, 1X, F8.3, 1X, I8, 1X, I4)
!
!***********************************************************************
!
! Build the list fire major point emissions speciated species
!# Speciate the emissions
    emis_nb_bins = max(2, (aqm_aerobins - 2)) ! no emissions for bins B and C
    
    nb_fire_me_species = ngas + nvocs + npm * emis_nb_bins
    allocate(fire_me_species(nb_fire_me_species))
    fire_me_species(1:ngas) = me_species_gas
    fire_me_species(ngas+1 : ngas+nvocs) = me_species_voc
    nsp = ngas + nvocs
    do sn = 1, npm
       do nbin = 1, emis_nb_bins
          write(zbin, '(Z1)') nbin
          nsp = nsp + 1
          fire_me_species(nsp) = trim(me_species_pm(sn)) // zbin
       end do
    end do

    cffeps_init = 1
     
    return
end function cffeps_init

