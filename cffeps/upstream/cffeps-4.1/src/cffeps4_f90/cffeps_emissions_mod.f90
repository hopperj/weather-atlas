!============================================================================!
!
! Projet / Project : GEM-MACH
! Fichier / File   : cffeps_emissions_mod.ftn90
! Creation         : Kerry Anderson 
!                  : (C To Fortran)
!                    A. Akingunola, J. Chen, and P. Makar - Fall 2018
! Description      : Species emissions profile for CFFEPS
!/* Emissions rates are based on CONSUME 3.0
!
!Page numbers refer to:
!
!    Consume 3.0 User's Guide
!    Susan J. Prichard, Roger D. Ottmar, and Gary K. Anderson
!    2004?

!Bulk densities for FBP fuel types are based on
!
!Anderson, K.R.  2000.  Incorporating smoldering into fire growth modelling.
!    Pages 31-36 in 3rd Symp. on Fire and Forest Meteorology, Jan. 9-14, 2000,
!    Long Beach, CA.  Am. Meteorol. Soc., Boston, MS.
!*/
!
!
!------------------ Wild Fire emission speciation profile  -------------
!
!------------------------ species list --------------------------------
! num   specie    Flaming     Smouldering   Residual
!----------------------------------------------------------------------
! 01    PM        23          34            34,99
! 02    PM10      16.05       27.38         40.75
! 03    PM2.5     13.60       23.20         34.53
! 04    CO        83          135           248
! 05    CO2       1662.33     1600          1383
! 06    CH4       3.23        7.32          9.94
! 07    NMHC      19.85       33.87         56.08
! 08    NOX       1.83        2.0           0.45
! 09    NH3       0.99        1.50          1.94
! 10    SO2       0.93        1.06          1.76
!============================================================================
!
module cffeps_emissions_mod

   use cffeps_mod,  only: fuel_size, MAX_TIMESTEPS, cffeps_timestep, &
                          cffeps_fueltypes, cffeps_fire_type, max_fuels
   implicit none
   public :: EmissionsCalc2, EmissionsOverTime2
   
   real(kind=4), dimension(max_fuels), parameter :: rhoBs = &
                    (/ 0.045, 0.034,   0.02, 0.031, 0.093,  0.05, &
                        0.02, 0.061,  0.061, 0.108, 0.108, 0.061, &
                       0.061, 0.078,  0.132,   0.1,    0.,    0., &
                          0.,  0./)
                         
!/* Values from Anderson 2000 in g/cm^3  and CFFEPS documentation*/
   real(kind=4), dimension(max_fuels), parameter :: rho2_consts = &
                    (/ 0.045, 0.019,  0.015, 0.022, 0.093, 0.030, &
                       0.100, 0.061,  -1.00,0.0265,0.0265, 0.041, &
                       0.041, 0.200,  0.500, 0.600, -1.00, -1.00, &
                       -1.00, -1.00/)
   real(kind=4), dimension(max_fuels), parameter :: rho4_consts = &
                    (/ 0.045, 0.034,  0.020, 0.029, 0.093, 0.050, &
                       0.100, 0.061,  -1.00, 0.071, 0.071, 0.061, &
                       0.061, 0.200,  0.500, 0.600, -1.00, -1.00, &
                       -1.00, -1.00/)
   real(kind=4), dimension(max_fuels), parameter :: rho6_consts = &
                    (/ 0.045, 0.051,  0.032, 0.045, 0.093, 0.050, &
                       0.050, 0.061,  -1.00,0.0795,0.0795, 0.084, &
                       0.084, 0.200,  0.300, 1.000, -1.00, -1.00, &
                       -1.00, -1.00/)
   real(kind=4), dimension(max_fuels), parameter :: rho8_consts = &
                    (/ 0.045, 0.056,  0.066, 0.059, 0.093, 0.050, &
                       0.000, 0.061,  -1.00, 0.082, 0.082, 0.112, &
                       0.112, 0.200,  0.300, 1.000, -1.00, -1.00, &
                       -1.00, -1.00/)
!
  contains
!============================================================================
!
   subroutine EmissionsCalc2(ifuel, sfc, tfc, dob_s, mcL, mcF, mcH, &
                             flaming,    smoldering,    residual,   &
                             mw_flaming, mw_smoldering, mw_residual)
      implicit none
       
      integer(kind=4), intent(in)  :: ifuel
      real(kind=4),    intent(in)  :: sfc, tfc
! Fire growth and plume energy
      real(kind=4),    intent(out) :: dob_s
! Fuel moisture content
      real(kind=4),    intent(in)  :: mcL, mcF, mcH     
! Flaming/Smoldering/Residual amounts in kg/m^2
      real(kind=4),    intent(out) :: flaming, smoldering, residual
      real(kind=4),    intent(out) :: mw_flaming, mw_smoldering, mw_residual

      real(kind=4)    :: rho2, rho4, rho6, rho8, L, F, H, rhoL, &
                         rhoF, rhoH, LFC, FFC, HFC, DOB, DOB_F
      character(len=FUEL_SIZE) :: fueltype
      
      fueltype = cffeps_fueltypes(ifuel)
!/* 1. Apply the average bulk density per fuel type to bulk densities for 
!      2, 4 6 and 8 cm depths */
!/* Use values from Anderson 2000 in g/cm^3 */
      select case (trim(fueltype))
         case('C1', 'C2', 'C3', 'C4', 'C6', 'C7', 'D1', &
              'M1', 'M2', 'M3', 'M4', 'S1', 'S2', 'S3')
            rho2 = rho2_consts(ifuel)
            rho4 = rho4_consts(ifuel)
            rho6 = rho6_consts(ifuel)
            rho8 = rho8_consts(ifuel)
         case default
            rho2 = rhoBs(ifuel)
            rho4 = rhoBs(ifuel)
            rho6 = rhoBs(ifuel)
            rho8 = rhoBs(ifuel)
      end select

! /* old numbers */
!       L = 2.
!       F = 5. - L
!       H = 25 - (F + L)
!       rhoL = rho2
!       rhoF = (2.0 * rho4 + rho6) / 3.0
!       rhoH = (rho6 + 2.0 * rho8) / 3.0

!/* 2. Calculate the bulk densities of the L (0-1.2 cm), F (1.2-7 cm) and 
!      H (7-18 cm) layers from the 2 cm depth data. */

!/* Nominal Fuel Depths [cm] from Van Wagner 1987, Table 1. */
      L = 1.2
      F = 7. - L
      H = 18. - (F + L)
      rhoL = rho2
      rhoF = ((2. - L) * rho2 + 2.0 * rho4 + 2.0 * rho6 + rho8) / F
      rhoH = rho8
         
!/* 2.a. If grass fuel type (O1), burn off the entire grass fuel load. 
!        Use the grass reduction values for flaming, smoldering and residual
!        combustion (see Table 2). */
      if (fueltype(1:2) == "O1") then
!/* These values are based on a personal communication with Bill de Groot */
         Flaming = 0.95 * tfc
         Smoldering = 0.05 * tfc
         Residual = 0.

!/* Water released [kg/m^2], including moisture released due to 
!   fuel moisture (mcL, mcF, mcH) and for chemical decomposition, 
         if (mcL > 0.0 .and. trim(cffeps_fire_type) == "wet") then
            mw_flaming    = 0.95 * tfc * mcL + 0.60 * Flaming
            mw_smoldering = 0.05 * tfc * mcL + 0.60 * Smoldering
         else
            mw_flaming    = 0.0
            mw_smoldering = 0.0
         end if
         mw_residual = 0.0
!    /* not calculated, not needed */
         DOB = 0.0 ; DOB_F = 0.0 ; DOB_S = 0.
         LFC = 0.0 ; FFC = 0.0 ; HFC = 0.
!         
      else
!
         if (fueltype(1:1) == "S") then
!/* 2.b. else, if slash, use the total fuel consumption (TFC). 
!           Use the slash reduction values for flaming, smoldering 
!           and residual combustion (see Table 2). */
!/* Slash  - p 194*/
            Flaming = 0.70 * tfc
            Smoldering = 0.15 * tfc
            Residual = 0.15 * tfc

!/* Water released [kg/m^2], including moisture released due to 
!   fuel moisture (mcL, mcF, mcH) and for chemical decomposition,
            if (mcL > 0.0 .and. mcF > 0.0 .and. mcH > 0.0 .and. &
                trim(cffeps_fire_type) == "wet") then
          ! calculate only when mcL, mcF, and mcF are all > 0. else 0.
          ! 0.60 = mass water produced during dry combustion 
          ! (C6H1206 + 6O2 -> 6 CO2 + 6H20) pg 157, Brown and Davis 2nd ed 1973
               mw_flaming    = 0.70 * tfc * mcL + 0.60 * Flaming
               mw_smoldering = 0.15 * tfc * mcF + 0.60 * Smoldering
               mw_residual   = 0.15 * tfc * mcH + 0.60 * Residual
            else
               mw_flaming    = 0.0
               mw_smoldering = 0.0
               mw_residual   = 0.0
            end if

!    /* not calculated, not needed */
            LFC = 0.0 ; FFC = 0.0 ; HFC = 0.
         else
!/* 2.c. else, burn off the LFH layers in sequence until the entire SFC is
!           accounted for.  Then use the crown fuel consumption (CFC) for 
!           any canopy burned.  Use the corresponding reduction values 
!           for flaming, smoldering and residual combustion (see Table 2). */

            if (sfc < (L * rhoL * 10.)) then
              !/* rhoL*10 give mass per square metre per cm of depth; 
              !   rho*20. gives mass per 2cm layer */
               LFC = sfc
            else
               LFC = L * rhoL * 10.
            end if

            if ((sfc - LFC) < (F * rhoF * 10.)) then
            !  /* rho*10 give mass per square metre per cm of depth; 
            !     rho*20. gives mass per 2cm layer */
               FFC = sfc - LFC
            else
               FFC = F * rhoF * 10.
            end if

            FFC = max(FFC, 0.)

            HFC = sfc - (LFC + FFC)
            HFC = max(HFC, 0.)

!/* Ground Fuels  - p. 166 */
            Flaming    = 0.90 * LFC + 0.10 * FFC + 0.00 * HFC
            Smoldering = 0.10 * LFC + 0.70 * FFC + 0.20 * HFC
            Residual   = 0.00 * LFC + 0.20 * FFC + 0.80 * HFC

!/* Trees  - p. 169 */
         !/* using mid story as compromise between over/mid and understory */
            Flaming    = Flaming   + 0.80 * (tfc - sfc) / 0.85
         !/* " / 0.85 " used to equate Flaming + Smouldering to CFC */
            Smoldering = Smoldering + 0.05 * (tfc - sfc) / 0.85

!/* Water released [kg/m^2], including moisture released due to 
!   fuel moisture (mcL, mcF, mcH) and for chemical decomposition
            if (mcL > 0.0 .and. mcF > 0.0 .and. mcH > 0.0 .and. &
                trim(cffeps_fire_type) == "wet") then
          ! calculate only when mcL, mcF, and mcF are all > 0. else 0.
          ! 0.60 = mass water produced during dry combustion 
          ! (C6H1206 + 6O2 -> 6 CO2 + 6H20) pg 157, Brown and Davis 2nd ed 1973
               mw_flaming    = 0.90 * LFC * mcL + 0.10 * FFC * mcF + &
                               0.00 * HFC * mcH + 0.60 * Flaming
               mw_smoldering = 0.10 * LFC * mcL + 0.70 * FFC * mcF + &
                               0.20 * HFC * mcH + 0.60 * Smoldering
               mw_residual   = 0.00 * LFC * mcL + 0.20 * FFC * mcF + &
                               0.80 * HFC * mcH + 0.60 * Residual
            else
               mw_flaming    = 0.0
               mw_smoldering = 0.0
               mw_residual   = 0.0
            end if

         end if
 !/* 3. Calculate depth of burn [cm] per stage */
         DOB = sfc / (rhoL * 10.)
         if (DOB > L) DOB = L + (sfc - L * rhoL * 10.) / (rhoF * 10.)
         if (DOB > (L + F)) &
            DOB = L + F + (sfc - L * rhoL * 10. - F * rhoF * 10.) / (rhoH * 10.)

!/* not quite but close enough */
         DOB_F = Flaming / (rhoL * 10);
         if (DOB_F > L) DOB_F = L + (Flaming - L * rhoL * 10.) / (rhoF * 10.)
         if (DOB_F > (L + F)) &
            DOB_F = L + F + (Flaming - L * rhoL * 10. - F * rhoF * 10.) / (rhoH * 10.)

         DOB_S = DOB - DOB_F

      end if
!
      return
   end subroutine EmissionsCalc2
!============================================================================
!
!/* new code used in CFFEPS - incorporates the residence time per stage */
!
!/*  In this approach, the residence times in each of the three are passed as
!    fractions of an hour.
!    It assumes that each phase is completed before the next begins
!    It also assumes that the emissions rate in each phase is constant during the phase

!    The return value is the extent of time the fire burn into the future (in timesteps )  */
   subroutine EmissionsOverTime2(Fs, Ss, Rs, jModel, imax, dob_s, fire_growth, &
                                 flaming, smoldering, residual, qplume_per_tfc)
      implicit none
      integer(kind=4),                        intent(in)  :: jModel 
      integer(kind=4),                        intent(out) :: imax 
      real(kind=4),                           intent(in)  :: fire_growth
      real(kind=4),                           intent(in)  :: qplume_per_tfc
      real(kind=4),                           intent(in)  :: dob_s
! Flaming/Smoldering/Residual amounts in kg/m^2
      real(kind=4),                           intent(in)  :: flaming,    &
                                                               smoldering, &
                                                               residual
      real(kind=4), dimension(MAX_TIMESTEPS), intent(out) :: Fs, Ss, Rs
      
      real(kind=4)  :: Fr, Sr, Rr, Ft, St, Rt, Fp, Sp, Rp, t1, t2, &
                         em_rate, inv_tstep
      real(kind=4)  :: lc_smoldering, lc_residual
! Energy release per stage */
      real(kind=4)  :: qflaming, qsmoldering, qresidual
! residence time for {flaming, smoldering, residual} combustion (hours)
      real(kind=4)  :: residence_flaming, residence_smoldering, &
                         residence_residual

      integer(kind=4) :: i

      Fr = 0.0 ; Sr = 0.0 ; Rr = 0.0
      
      !/* residence time for flaming combustion (hours) -- remains the same */
      residence_flaming = 0.25
            ! /* this is new, based on the assumption that a fire smolders
            !    at 1 cm/hour (Dan Thompson) */
      residence_smoldering = dob_s * 0.5
            !/* split equally between smoldering and residual */
      residence_residual = dob_s * 0.5
      if (dob_s <= 0.0) then
         lc_smoldering = 0.0
         lc_residual   = 0.0
      else
         lc_smoldering = smoldering
         lc_residual   = residual
      end if


!/* 1. Calculate the total residence time in hours for flaming, smoldering and residual stages */
!//     recalculated from hours to timesteps 2018-07-30
      imax = int(ceiling((residence_flaming + residence_smoldering + &
                          residence_residual) /  cffeps_timestep))
!
      if (imax >= MAX_TIMESTEPS) imax = MAX_TIMESTEPS-1

      inv_tstep = 1.0 / cffeps_timestep
      if (jModel >= 0) then

!/* 2. Calculate the emissions rates [tonnes/hr] (or energy if jModel <0) for 
!      flaming, smoldering and residual stages */

!//   tonnes/hr =             ha/timestep  / hours/timestep *      tonnes/ha
         em_rate = 1.0e-3 * fire_growth * inv_tstep * 10.0
         Fr = em_rate * flaming          ! / residence_flaming   
         Sr = em_rate * lc_smoldering    ! / residence_smoldering; 
         Rr = em_rate * lc_residual      ! / residence_residual; 

!/* emissions factors (applied in emission speciation routine)
!   are now assumed to be in [g/kg] (not [lbs/ton] as described below) 
!   - KRA 2017-02-06 */

!/*                 [lbs/ton]     [lbs/ton]     [ha]         [kg/m^2]         [hours]

!   emissions factors are in lbs/ton    (changed to [g/kg] - 2017-02-06)
!   divide by 2000 to convert lbs/ton to unitless (cancels units of emissions factors)
!   fire growth is in hectares
!   flaming is a fraction of the TFC in kg/m^2 (coverted to tonnes per 
!                hectare by multiplying by 10)
!   residence_flaming]

!   answer is in [metric] tonnes per hour
!*/
    
      else if (jModel == -1) then
     !/* if jModel == -1, use this technique to come up with energy per hour */
     !//               J/timesteps    / hrs/timestep
     
!/*   Calculate energy release per stage */
         qflaming = qplume_per_tfc * flaming
         qsmoldering = qplume_per_tfc * lc_smoldering
         qresidual = qplume_per_tfc * lc_residual
         
         Fr = qflaming * inv_tstep    ! / residence_flaming
         Sr = qsmoldering * inv_tstep ! / residence_smoldering
         Rr = qresidual * inv_tstep   ! / residence_residual
!        
      else    !/*  use this technique to come up with fuel consumption per hour */
         Fr = flaming * inv_tstep       ! / residence_flaming;
         Sr = lc_smoldering * inv_tstep ! / residence_smoldering;
         Rr = lc_residual * inv_tstep   ! / residence_residual;
      end if
      
!/* Resident times (hours) */
      Ft = residence_flaming
      St = residence_smoldering
      Rt = residence_residual

!/* Partial Resident times (hours) */
      Fp = 0.0 ; Sp = 0.0 ; Rp = 0.0

!/* 3. Stepping through each timestep */
      if ((Fr + Sr + Rr) > 0) then
         do i = 1, imax
            t1 = (i - 1) * cffeps_timestep
            t2 = t1 + cffeps_timestep
!/* 3.a. calculate partial residence times remaining in decimal hours */
            if (t2 <= Ft) then
               Fp = cffeps_timestep
            else
               if (t1 < Ft) then
                  Fp = Ft - t1 - aint(Ft - t1)
               else
                  Fp = 0.0
               end if
            end if

            if (t2 <= (Ft + St)) then
               Sp = cffeps_timestep - Fp
            else
               if (t1 < Ft + St) then
                 Sp = Ft + St - t1 - aint(Ft + St - t1) - Fp
               else
                  Sp = 0.0
               end if
            end if

            if (t2 <= Ft + St + Rt) then
               Rp = cffeps_timestep - Sp - Fp
            else
               if (t1 < Ft + St + Rt) then
                  Rp = Ft + St + Rt - t1 - aint(Ft + St + Rt - t1) - Sp - Fp
               else
                  Rp = 0.0
               end if
            end if

!/* 3.b. calculate the emissions for the partial hour */
!//     recalculated from hours to timesteps 2018-07-30

!// tonnes/timestep = tonnes/hr * hrs * hrs/timestep / hrs
            if (residence_flaming > 0.0) then
               Fs(i) = Fr * Fp * cffeps_timestep / residence_flaming
            else
               Fs(i) = 0
            end if

            if(residence_smoldering > 0.0) then
                Ss(i) = Sr * Sp * cffeps_timestep / residence_smoldering
            else
                Ss(i) = 0.0
            end if

            if (residence_residual > 0.0) then
               Rs(i) = Rr * Rp * cffeps_timestep / residence_residual
            else
               Rs(i) = 0.0
            end if
         end do
         
      else
         Fs = 0.0; Ss = 0.0; Rs = 0.0
      end if

      return

   end subroutine EmissionsOverTime2
   
end module cffeps_emissions_mod
