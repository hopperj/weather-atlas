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
! Fichier / File   : cffeps_readfst.ftn90
! Creation         : A. Akingunola, J. Chen, P. Makar, and Kerry Anderson 
!                     - Fall 2018
! Description      : Extract MET. fields needed by CFFEPS from an FST files
!
!============================================================================
!
 subroutine readfst(feps, met, elev, nspots, hyb_filename, validity_date, &
                    istatus)
!
   use vGrid_Descriptors, only: vgrid_descriptor, vgd_new, vgd_get, &
                                vgd_levels, VGD_OK, vgd_free !, vgd_print
   use cffeps_mod,        only: met_type, met_levels, NB_CHAR_PATH, feps_type
                                
   implicit none
!
   integer,                            intent(in)  :: nspots
   integer,                            intent(out) :: istatus
   type(met_type),  dimension(nspots), intent(out) :: met
   type(feps_type), dimension(nspots), intent(in)  :: feps
   real,            dimension(nspots), intent(out) :: elev
   character(len=NB_CHAR_PATH),        intent(in)  :: hyb_filename
   character(len=12),                  intent(out) :: validity_date
!      
   real, dimension(nspots) :: latin, lonin0
!
   integer :: ix, jy, ij, kk, ik
   integer :: fu_hyb, fu_pres
   integer :: ip1
!
   integer, save ::     dyngrid_ni, dyngrid_nj
      
   integer ::     dyngrid_id, dyn_ip1, dyn_ip2, dyn_ip3
   integer ::     dyngrid_ig1, dyngrid_ig2, dyngrid_ig3, dyngrid_ig4
   character(len=4) :: dyngrid_type

   integer :: nj_bidon, nk_bidon, nbits_bidon, datyp_bidon
   integer :: dateo_bidon, deet_bidon, npas_bidon, npas
   integer :: ip1_bidon, ip2_bidon, ip3_bidon,  ig1_bidon, ig2_bidon, ig3_bidon, ig4_bidon
   integer :: swa_bidon, lng_bidon, dltf_bidon, ubc_bidon, e1_bidon,  e2_bidon,  e3_bidon
   character(len=2) :: typvar_bidon, grtyp_bidon
   character(len=4) :: nomvar_bidon, nomvar
   character(len=12) :: etiket_bidon, etiket, datev
       
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
   real, allocatable, dimension(:, :)    :: uu, vv, hr, hu, gz, p0
   real, allocatable, dimension(:, :, :) :: tta, gza
      
   integer, parameter :: ip1s = 59868832
   real(kind=4), parameter  :: tcdk = 273.16
!
   integer :: datestamp, timestamp
   character(len=3) :: model_hr
!
!        Staggerred levels ip1 lists and vertical coordinates
   integer                                :: nkT, ip1th, ip1mo, ip1gz
   integer, dimension(:),     pointer     :: ip1vT=>null() !, ip1vM
   real,    dimension(:),     pointer     :: hybvT=>null() !, hybvM
   type(vgrid_descriptor)                 :: vgd
      
   real, dimension(nspots) :: dynlat2x, dynlon2y
   real, dimension(nspots) :: windspd, lonin
   real :: tts
   logical :: do_once = .true.
!
!  Fst functions
!  External functions
   integer, external :: fnom, fstouv, fstinf, fstinl, fstprm, fstlir,       &
                        fstopc, newdate, ezqkdef, ezsetopt, gdrls, gdxyfll, &
                        fclos, fstfrm

!   Turn off FST information messages
   ier = fstopc('MSGLVL', 'SYSTEM', 0)
!
   fu_hyb  = 16
   fu_pres = 18
!
   do ij = 1, nspots
      latin(ij) = feps(ij)%lat
      lonin(ij) = feps(ij)%lon + 360.0
   end do

   if (fnom(fu_hyb, trim(hyb_filename), 'RND+OLD+R/O', 0) < 0) then
      write(*, *) '### Error in reading fst file ###'
      write(*, *) '# fnom failed for:', trim(hyb_filename)
      istatus = -1
      return
   end if
   if (fstouv(fu_hyb, 'RND') < 0) then
      write(*, *) '### Error in em_open_fstfile ###'
      write(*, *) '# fstouv failed for:', trim(hyb_filename)
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

  !*******Retrieve the vertical co-ordinate parameters; ******
     ! Use the 1.5m level TT as a proxy to probe the dyn_grid toctoc
   ier = vgd_new(vgd, unit = fu_hyb, format = 'fst', ip1 = dyngrid_ig1, &
                 ip2 = dyngrid_ig2)
   if (ier /= VGD_OK) then
      write(*, *) 'readfst error: cannot access the coordinate descriptor'
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
      write(*, *) 'Error in retrieving vertical coordinate param'
      return
   end if

   if (nkT < met_levels) then
      write(*, *) 'Number of thermodynamic levels in model less than met_levels'
      write(*, *) 'Abort !!!'
      return
   end if
    ! Get the surface GZ ip1 value
   ip1gz = ip1vT(nkT - 1)
!  
   ier = ezsetopt('INTERP_DEGREE', 'NEAREST')
   ier = ezsetopt('VERBOSE', 'NO')
   dyngrid_id = ezqkdef(dyngrid_ni, dyngrid_nj ,dyngrid_type, dyngrid_ig1, &
                        dyngrid_ig2, dyngrid_ig3, dyngrid_ig4, fu_hyb)
!
   ! Find the coordinates of all the hotspots contained within the dyngrid:
   ier = gdxyfll(dyngrid_id, dynlat2x, dynlon2y, latin, lonin, nspots)

   ! Check if all the hotspots are contained within the model grid
   do ij = 1, nspots
      if ((dynlat2x(ij) > real(dyngrid_ni)) .or. & 
          (dynlon2y(ij) > real(dyngrid_nj)) .or. &
          (dynlat2x(ij) < 1.0) .or. (dynlon2y(ij) < 1.0)) then
      write(*, *) 'hostpot ', ij, latin(ij), lonin(ij), &
                  ' is outside of the model grid boundaries'
      end if
   end do
         
   !  Allocate array space for desired fields:
   allocate(uu(dyngrid_ni, dyngrid_nj))
   allocate(vv(dyngrid_ni, dyngrid_nj))
   allocate(gz(dyngrid_ni, dyngrid_nj))
   allocate(hr(dyngrid_ni, dyngrid_nj))
   allocate(hu(dyngrid_ni, dyngrid_nj))
   allocate(p0(dyngrid_ni, dyngrid_nj))

   allocate(tta(dyngrid_ni, dyngrid_nj, met_levels))
   allocate(gza(dyngrid_ni, dyngrid_nj, met_levels))
                
   ier = fstlir(hr, fu_hyb, nx, ny, nz, -1, ' ', ip1th, -1, -1, ' ', 'HR')
   ier = fstlir(hu, fu_hyb, nx, ny, nz, -1, ' ', ip1th, -1, -1, ' ', 'HU')
   ier = fstlir(gz, fu_hyb, nx, ny, nz, -1, ' ', ip1gz, -1, -1, ' ', 'GZ')
                      
   ier = fstlir(p0, fu_hyb, nx, ny, nz, -1, ' ', -1, -1, -1, ' ', 'P0')
   p0 = p0 * 100.0  ! Convert mb to Pa
   
   ier = fstlir(uu, fu_hyb, nx, ny, nz, -1, ' ', ip1mo, -1, -1, ' ', 'UU')
   ier = fstlir(vv, fu_hyb, nx, ny, nz, -1, ' ', ip1mo, -1, -1, ' ', 'VV')

   ! Diagnostic (near-surface) level air temperature
   ier = fstlir(tta(:, :, 1), fu_hyb, nx, ny, nz, -1, ' ', ip1th, -1, -1, &
                ' ', 'TT')
   do kk = 2, met_levels
      ik = nkT - kk ! actually => (nkT - 1) - kk + 1
      ip1 = ip1vT(ik)
      ier = fstlir(tta(:, :, kk), fu_hyb, nx, ny, nz, -1, ' ', ip1, -1, -1, &
                   ' ', 'TT')
      ier = fstlir(gza(:, :, kk), fu_hyb, nx, ny, nz, -1, ' ', ip1, -1, -1, &
                   ' ', 'GZ')
   end do
      
   ier = newdate(e1_bidon, datestamp, timestamp, -3)
      
   do ij = 1, nspots
      ix = nint(dynlat2x(ij))
      jy = nint(dynlon2y(ij))
      elev(ij) = gz(ix, jy) * 10.0
      tts = tta(ix, jy, 1) + tcdk
      met(ij)%hus = hu(ix, jy)
      ! Estimate the dew point temperature [K] from RH, using CFFEPS formulation
      ! taking from Irabarne and Godson (1973) [VII-6]
      met(ij)%Td = 1.0 / (-4.25E-4 * log10(hr(ix, jy)) + 1.0 / tts)
      met(ij)%ws = sqrt(uu(ix, jy)**2 + vv(ix, jy)**2)

      ! Set the first model level at the surface
      met(ij)%P(1) = p0(ix, jy)
      met(ij)%T(1) = tts
      met(ij)%Z(1) = 0.0 !Set to the surface
        ! Aproximate vertical pressure at the found level
      do kk = 2, met_levels
         ik = nkT - kk ! actually => (nkT - 1) - kk + 1
         met(ij)%P(kk) = p0(ix, jy) * hybvT(ik)
         met(ij)%T(kk) = tta(ix, jy, kk) + tcdk
         ! met%Z is the model height above the surface [AGL]
         met(ij)%Z(kk) = gza(ix, jy, kk) * 10.0 - elev(ij)
      end do
   end do
   write(datev(1:8), '(i8.8)') datestamp
   write(datev(9:12), '(i4.4)') timestamp / 10000
   
   validity_date = datev

   !  Release ezscint grid
!  ier = gdrls(dyngrid_id)
         
   ! Free the vertical grid descriptor
   ier = vgd_free(vgd)
      
   deallocate(uu, vv, gz, p0)
   deallocate(hr, hu)
   deallocate(tta, gza)
      
   ier = fstfrm(fu_hyb)
   ier = fclos(fu_hyb)
   
   return
!
 end subroutine readfst