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
! Fichier / File   : mach_readfst.ftn90
! Creation         : A. Akingunola, J. Chen, P. Makar, and Kerry Anderson
!                     - Fall 2018
! Description      : Extract MET. fields needed by CFFEPS from an FST files
!
!============================================================================
!
module mach_readfst_mod
 implicit none
 private
 public :: mach_readfst

 contains
 !/@*
 subroutine mach_readfst(lat, lon, nspots, hyb_filename, met, datev, istep, &
                         valid_hotspot, istatus)
!
   use vGrid_Descriptors, only: vgrid_descriptor, vgd_new, vgd_get, &
                                vgd_levels, VGD_OK, vgd_free !, vgd_print
   use mach_cffeps_mod,   only: met_type, met_levels, NB_CHAR_PATH, &
                                cffeps_diurnal

   implicit none
!
   integer,                            intent(in)    :: nspots
   integer,                            intent(in)    :: istep
   integer,                            intent(out)   :: istatus
   logical,         dimension(nspots), intent(inout) :: valid_hotspot
   real,            dimension(nspots), intent(in)    :: lat
   real,            dimension(nspots), intent(in)    :: lon
   character(len=NB_CHAR_PATH),        intent(in)    :: hyb_filename
   type(met_type),  dimension(nspots), intent(out)   :: met
   character(len=12),                  intent(out)   :: datev
!
   integer :: ix, jy, ij, kk, ik
   integer :: fu_hyb, fu_pres
   integer :: ip1
!
   integer, save :: dyngrid_ni, dyngrid_nj, phygrid_ni, phygrid_nj

   integer ::     dyngrid_id, dyn_ip1, dyn_ip2, dyn_ip3, phygrid_id
   integer ::     dyngrid_ig1, dyngrid_ig2, dyngrid_ig3, dyngrid_ig4
   integer ::     phygrid_ig1, phygrid_ig2, phygrid_ig3, phygrid_ig4
   character(len=4) :: dyngrid_type, phygrid_type

   integer :: nj_bidon, nk_bidon, nbits_bidon, datyp_bidon
   integer :: dateo_bidon, deet_bidon, npas_bidon, npas
   integer :: ip1_bidon, ip2_bidon, ip3_bidon,  ig1_bidon, ig2_bidon, ig3_bidon, ig4_bidon
   integer :: swa_bidon, lng_bidon, dltf_bidon, ubc_bidon, e1_bidon,  e2_bidon,  e3_bidon
   character(len=2) :: typvar_bidon, grtyp_bidon
   character(len=4) :: nomvar_bidon, nomvar
   character(len=12) :: etiket_bidon, etiket

   integer :: dateo_grid, deet_grid, npas_grid, nbits_grid, datyp_grid
   integer :: ip1_grid, ip2_grid, ip3_grid, dyn_ig1, dyn_ig2
   integer :: ig1_grid, ig2_grid, ig3_grid, ig4_grid, dyn_ig3, dyn_ig4
   integer :: swa_grid, lng_grid, dltf_grid, ubc_grid
   integer :: e1_grid, e2_grid, e3_grid
   character(len=2) :: typvar_grid, grtyp_grid
   character(len=4) :: nomvar_grid
   character(len=12) :: etiket_grid
!
   integer :: key, ier, nx, ny, nz
!
   real, allocatable, dimension(:, :)    :: uu, vv, hu, gz, p0, ta, rt
   real, allocatable, dimension(:, :, :) :: tta, gza

   integer, parameter :: ip1s = 59868832
   real(kind=4), parameter  :: tcdk = 273.16
   real(kind=4), parameter  :: pi = 3.1415926
!
   integer :: datestamp, timestamp
   character(len=3) :: model_hr
!
!        Staggerred levels ip1 lists and vertical coordinates
   integer                                :: nk, nkT, ip1th, ip1mo, ip1gz
   integer, dimension(:),     pointer     :: ip1vT=>null() !, ip1vM
   real,    dimension(:),     pointer     :: hybvT=>null() !, hybvM
   type(vgrid_descriptor)                 :: vgd

   real,    dimension(nspots) :: dynlat2x, dynlon2y
   real,    dimension(nspots) :: wspd, wdir, precip
   logical :: do_once = .true.
!
!  Fst functions
!  External functions
   integer, external :: fnom, fstouv, fstinf, fstinl, fstprm, fstlir,       &
                        fstopc, newdate, ezqkdef, ezsetopt, gdrls, gdxyfll, &
                        fclos, fstfrm, gdllwdval, gdllsval

!  Turn off FST information messages
   ier = fstopc('MSGLVL', 'SYSTEM', 0)
!  Turn on
!  ier = fstopc('MSGLVL', 'INFORM', 0)

!
   fu_hyb  = 16
   fu_pres = 18
!
   if (fnom(fu_hyb, trim(hyb_filename), 'RND+OLD+R/O', 0) < 0) then
      write(0, *) '### Error in reading fst file ###'
      write(0, *) '# fnom failed for:', trim(hyb_filename)
      istatus = -1
      return
   end if
   if (fstouv(fu_hyb, 'RND+OLD') < 0) then
      write(0, *) '### Error in em_open_fstfile ###'
      write(0, *) '# fstouv failed for:', trim(hyb_filename)
      istatus = -1
      return
   end if

   !Use the hourly info to obtain the time info e1_bidon
   key = fstinf(fu_hyb, nx, ny, nz, -1, ' ',  -1, -1, -1, ' ', 'TT')
   ier = fstprm(key, dateo_bidon, deet_bidon, npas_bidon,      &
                dyngrid_ni, dyngrid_nj, nk_bidon, nbits_bidon, &
                datyp_bidon, ip1_bidon, ip2_bidon, ip3_bidon,  &
                typvar_bidon, nomvar_bidon, etiket_bidon, dyngrid_type, &
                dyngrid_ig1, dyngrid_ig2, dyngrid_ig3, dyngrid_ig4,     &
                swa_bidon, lng_bidon, dltf_bidon, ubc_bidon,   &
                e1_bidon, e2_bidon, e3_bidon)

   ier = ezsetopt('INTERP_DEGREE', 'NEAREST')
   ier = ezsetopt('VERBOSE', 'NO')
   dyngrid_id = ezqkdef(dyngrid_ni, dyngrid_nj, dyngrid_type, dyngrid_ig1, &
                        dyngrid_ig2, dyngrid_ig3, dyngrid_ig4, fu_hyb)
!
   ! Find the coordinates of all the hotspots contained within the dyngrid:
   ier = gdxyfll(dyngrid_id, dynlat2x, dynlon2y, lat, lon, nspots)

   ip1gz = 93423264 !ip1vT(nkT - 1)
   if (istep == 1) then
   ! Check if all the hotspots are contained within the model grid

      do ij = 1, nspots
         if ((dynlat2x(ij) > real(dyngrid_ni)) .or. &
             (dynlon2y(ij) > real(dyngrid_nj)) .or. &
             (dynlat2x(ij) < 1.0) .or. (dynlon2y(ij) < 1.0)) then
            write(*, *) 'hotspot ', ij, lat(ij), lon(ij), &
                        ' is outside of the model grid boundaries'
            valid_hotspot(ij) = .false.
         else
            valid_hotspot(ij) = .true.
         end if
      end do

      if (.not. any(valid_hotspot)) then
         write(*, *) 'No fire hotspot within the piloting model domain, ABORT!! '
         istatus = 0
         return
      end if

   end if

  ! At this point, we assume the valid hotspots have once been checked in
  ! cffeps_init_mod, and thus all the hotspots from here on are valid

  !*******Retrieve the vertical co-ordinate parameters; ******
     ! Use the 1.5m level TT as a proxy to probe the dyn_grid toctoc
   ier = vgd_new(vgd, unit = fu_hyb, format = 'fst', ip1 = dyngrid_ig1, &
                 ip2 = dyngrid_ig2)
   if (ier /= VGD_OK) then
      write(0, *) 'readfst error: cannot access the coordinate descriptor'
      istatus = -1
      return
   end if
   istatus = 1
   !if (vgd_get(vgd,'NL_M - number of momentum levels', nkM) /= VGD_OK) ier = -1
   ier = vgd_get(vgd,'NL_T - number of thermodynamic levels', nkT)
   if (ier /= VGD_OK) istatus = min(-1, istatus)
   ier = vgd_get(vgd,'DIPM - IP1 of diagnostic level (m)', ip1mo)
   if (ier /= VGD_OK) istatus = min(-1, istatus)
   ier = vgd_get(vgd,'DIPT - IP1 of diagnostic level (t)', ip1th)
   if (ier /= VGD_OK) istatus = min(-1, istatus)
   !if (vgd_get(vgd,'VIPM - level ip1 list (m)', ip1vM) /= VGD_OK) ier = -1
   ier = vgd_get(vgd,'VIPT - level ip1 list (t)', ip1vT)
   if (ier /= VGD_OK) istatus = min(-1, istatus)
   !if (vgd_get(vgd,'VCDM - vertical coordinate (m)', hybvM) /= VGD_OK) ier = -1
   ier = vgd_get(vgd,'VCDT - vertical coordinate (t)', hybvT)
   if (ier /= VGD_OK) istatus = min(-1, istatus)
   if (istatus < 0) then
      write(0, *) 'Error in retrieving vertical coordinate param'
      return
   end if

   if (nkT < met_levels) then
      write(0, *) 'Number of thermodynamic levels in model less than met_levels'
      write(0, *) 'Abort !!!'
      return
   end if
   nk = nkT - 1
!
   !  Allocate array space for desired fields:
   allocate(uu(dyngrid_ni, dyngrid_nj))
   allocate(vv(dyngrid_ni, dyngrid_nj))
   allocate(gz(dyngrid_ni, dyngrid_nj))
   allocate(hu(dyngrid_ni, dyngrid_nj))
   allocate(p0(dyngrid_ni, dyngrid_nj))
   allocate(ta(dyngrid_ni, dyngrid_nj))

   allocate(tta(dyngrid_ni, dyngrid_nj, met_levels))
   allocate(gza(dyngrid_ni, dyngrid_nj, met_levels))

   ier = fstlir(hu, fu_hyb, nx, ny, nz, -1, ' ', ip1th, -1, -1, ' ', 'HU')
   istatus = min(istatus, ier)
   ier = fstlir(gz, fu_hyb, nx, ny, nz, -1, ' ', ip1gz, -1, -1, ' ', 'GZ')
   istatus = min(istatus, ier)
   ier = fstlir(p0, fu_hyb, nx, ny, nz, -1, ' ', -1, -1, -1, ' ', 'P0')
   istatus = min(istatus, ier)
   ier = fstlir(uu, fu_hyb, nx, ny, nz, -1, ' ', ip1mo, -1, -1, ' ', 'UU')
   istatus = min(istatus, ier)
   ier = fstlir(vv, fu_hyb, nx, ny, nz, -1, ' ', ip1mo, -1, -1, ' ', 'VV')
   istatus = min(istatus, ier)
   if (istatus < 0) then
      write(0, *) 'Error in surface variable(s): HU, GZ, P0, UU, VV'
      write(0, *) 'file:', trim(hyb_filename)
      write(0, *) 'TT ip1:',ip1th,'GZ ip1:',ip1gz,'UU VV ip1:',ip1mo
      return
   end if

   ! Diagnostic (near-surface) level air temperature
   ier = fstlir(ta, fu_hyb, nx, ny, nz, -1, ' ', ip1th, -1, -1, ' ', 'TT')
   do kk = 1, met_levels
      ik = nk - kk ! Starting with the level above the diagnostic level
      ip1 = ip1vT(ik)
      ier = fstlir(tta(:, :, kk), fu_hyb, nx, ny, nz, -1, ' ', ip1, -1, -1, &
                   ' ', 'TT')
      istatus = min(istatus, ier)
      ier = fstlir(gza(:, :, kk), fu_hyb, nx, ny, nz, -1, ' ', ip1, -1, -1, &
                   ' ', 'GZ')
      istatus = min(istatus, ier)
      if (istatus < 0) then
         write(0, *) 'Error in retrieving vertical TT or GZ variables'
         write(0, *) 'file:', trim(hyb_filename),' ip1:',ip1
         return
      endif
   end do

   ier = newdate(e1_bidon, datestamp, timestamp, -3)

   !  Convert model winds uu,vv to wind speed and direction at the hotspot locations:
   ier = gdllwdval(dyngrid_id, wspd, wdir, uu, vv, lat, lon, nspots)

   wspd = wspd * 1.852      !  Convert wind speed from knots to km/hr:
   wdir = wdir * pi / 180.0 !  Convert wind direction from degrees to radians

   ! Obtain the precipitation rate fields from the physics grid
   if (cffeps_diurnal /= 'OFF') then
      key = fstinf(fu_hyb, nx, ny, nz, -1, ' ',  -1, -1, -1, ' ', 'RT')
      if (key <= 0) then
         write(0, *) 'Error in PR field from file:', trim(hyb_filename)
         istatus = -1
         return
      end if
      ier = fstprm(key, dateo_bidon, deet_bidon, npas_bidon,      &
                   phygrid_ni, phygrid_nj, nk_bidon, nbits_bidon, &
                   datyp_bidon, ip1_bidon, ip2_bidon, ip3_bidon,  &
                   typvar_bidon, nomvar_bidon, etiket_bidon, phygrid_type, &
                   phygrid_ig1, phygrid_ig2, phygrid_ig3, phygrid_ig4,     &
                   swa_bidon, lng_bidon, dltf_bidon, ubc_bidon,   &
                   e1_bidon, e2_bidon, e3_bidon)

      phygrid_id = ezqkdef(phygrid_ni, phygrid_nj, phygrid_type, phygrid_ig1, &
                           phygrid_ig2, phygrid_ig3, phygrid_ig4, fu_hyb)

      allocate(rt(phygrid_ni, phygrid_nj))
      ier = fstlir(rt, fu_hyb, nx, ny, nz, -1, ' ', -1, -1, -1, ' ', 'RT')
      istatus = min(istatus, ier)
      if (istatus < 0) then
         write(0, *) 'Error in retrieving RT from file:', trim(hyb_filename)
         return
      end if
      ier = gdllsval(phygrid_id, precip, rt, lat, lon, nspots)

      precip = precip * 3.6e6  ! Convert total precipitation from m/s to mm/hr
   else
      precip = 0.0
   end if

   do ij = 1, nspots
      if (.not. valid_hotspot(ij)) cycle

      ix = nint(dynlat2x(ij))
      jy = nint(dynlon2y(ij))

      ! Set the first model level at the surface
      met(ij)%ta = ta(ix, jy) + tcdk
      met(ij)%hus = hu(ix, jy)
      met(ij)%ps = p0(ix, jy)   !  // surface pressure [mb]
!      met(ij)%ws = sqrt(uu(ix, jy)**2 + vv(ix, jy)**2)
!      met(ij)%wd = 180.0 / pi * atan(vv(ix, jy) / (uu(ix, jy) + 1.0e-15)) + 180.0
      met(ij)%ws = wspd(ij)
      met(ij)%wd = wdir(ij)
      met(ij)%pr = precip(ij)

        ! Aproximate vertical pressure at the found level
      do kk = 1, met_levels
         ik = nk - kk
         met(ij)%P(kk) = p0(ix, jy) * hybvT(ik) * 1.0e2 ! [Pa]
         met(ij)%T(kk) = tta(ix, jy, kk) + tcdk
         ! met%Z is the model height above the surface [AGL]
         met(ij)%Z(kk) = (gza(ix, jy, kk) - gz(ix, jy))* 10.0
      end do
   end do
   write(datev(1:8), '(i8.8)') datestamp
   write(datev(9:12), '(i4.4)') timestamp / 10000

   istatus = 1

   !  Release ezscint grid
!  ier = gdrls(dyngrid_id)

   ! Free the vertical grid descriptor
   ier = vgd_free(vgd)
   istatus = min(istatus, ier)

   deallocate(uu, vv, p0, ta)
   deallocate(hu, gz)
   deallocate(tta, gza)

   ier = fstfrm(fu_hyb)
   istatus = min(istatus, ier)
   ier = fclos(fu_hyb)
   istatus = min(istatus, ier)

   return
!
 end subroutine mach_readfst

end module mach_readfst_mod
