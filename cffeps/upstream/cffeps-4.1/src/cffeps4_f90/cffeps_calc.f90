!============================================================================!
!
! Projet / Project : GEM-MACH
! Fichier / File   : cffeps_calc.ftn90
! Creation         : Kerry Anderson 
!                  : (C To Fortran)
!                    A. Akingunola, J. Chen, and P. Makar - Fall 2018
! Description      : Energy Balance of a Fire required for Plume Rise
!                    Anderson, K.R.; Pankratz, A; Mooney, C. 2011.   
!                    A thermodynamic approach to estimating smoke plume heights.
!                    In 9th Symp. on Fire and Forest Meteorology, 
!                    Oct 18-20, 2011.  Palm Springs, CA.
!                    Am. Meteorol. Soc., Boston, MS.
!
!                    Bulk densities for FBP fuel types are based on;
!
!                  Anderson, K.R.  2000.
!                  Incorporating smoldering into fire growth modelling.
!                  Pages 31-36 in 3rd Symp. on Fire and Forest Meteorology,
!                  Jan. 9-14, 2000, Long Beach, CA. Am. Meteorol. Soc., Boston, MS.
!============================================================================
 subroutine cffeps_calc(feps, emissions, r_smoke, dz, met, mws, cmcDj, &
                        cmcUTC_in, istep)
   use cffeps_mod,           only: feps_type, fbp_type, met_type,       &
                                   emissions_type, fuel_size,           &
                                   NB_CHAR_PATH, MAX_TIMESTEPS, weight, & 
                                   cffeps_nspec, cffeps_reset,          &
                                   cffeps_ldt, cffeps_fire_shape,       &
                                   cffeps_fire_type, cffeps_timestep,   &
                                   max_fuels, cffeps_fueltypes,         &                                        
                                   cmcUTC0, cmcDj0, met_levels
   use cffeps_emissions_mod, only: EmissionsCalc2, EmissionsOverTime2
   use cffeps_plume_mod,     only: cffeps_plumecalc, cffeps_plumecalc2
   use cffeps_fbp_mod,       only: cffeps_fbpcalc

   implicit none
      
   type(feps_type),      intent(inout) :: feps
   type(emissions_type), intent(inout) :: emissions
   type(met_type),       intent(in)    :: met
   integer(kind=4),      intent(in)    :: cmcDj, istep
   real(kind=4),         intent(in)    :: cmcUTC_in
   real(kind=4),         intent(out)   :: dz      ! plume height in metres
   real(kind=4),         intent(out)   :: r_smoke ! mixing ratio of smoke to clear air (g/kg)
   real(kind=4),         intent(inout), dimension(MAX_TIMESTEPS) :: mws
      
   real(kind=4), parameter  :: pi = 3.1415926
                                   
   type(fbp_type) :: fbp
   real(kind=4), dimension(MAX_TIMESTEPS) :: Fs, Ss, Rs
   real(kind=4) :: mplume       ! mass of the plume volume
   real(kind=4) :: growth       ! change in fire size over last timestep
   real(kind=4) :: lapse_rate   ! lapse rate [oC/m]
   real(kind=4) :: Qplume       ! energy in the plume: used when directly
                                  ! calculating the plume height from energy
                                  ! (in stand alone module)
   real(kind=4)  :: mw0           ! Mass of water released from fuel moisture 
                                ! and due to combustion
   real(kind=4)  :: timezone, rsum, detectionLST, detectionUTC,     &
                    cmcLST, cmcUTC, cmcUTCo, discovery, t1, t2, dt, &
                    p, d, perimeter, a, diameter, ws, dob_s, Qbb, tsurf
!   real(kind=4)  :: x, y, FFMC, FFMCt, FFMCy, FFMCnoon ! FFMC Adjustment
   real(kind=4)  :: mcL, mcF, mcH  ! Moisture content      
   real(kind=4)  :: dz8, dz7, dz5, l8, l7, dzmax, estarea2, parea
   real(kind=4)  :: flaming, smoldering, residual, qplume_per_tfc
   real(kind=4)  :: mw_flaming, mw_smoldering, mw_residual
   integer(kind=4) :: i, ij, iMax, ifuel, jModel, thisLST

   real(kind=4), parameter :: dzmin = 0.0
   ! iref* are the reference levels for the average lapse rate cffeps_plumeCalc
   integer(kind=4) :: ik, kk, iref2, iref3, iref4, iref5, l5
   
! Set fuel type index
   ifuel = feps%fueltype
!
! Return (exit) immediately if fuel type is unknown or there's no fire!
   if (ifuel > 18 .or. feps%ffmc <= 0.0 .or. feps%bui <= 0.0) then
!      
      growth = 0.0
      r_smoke = 0.0
      dz = 0
      mplume = 0
      qplume = 0.0
      
      feps%area = 0.0
      feps%totalemissions = 0.0
      feps%Qo = 0.0
      feps%Qs = 0.0
!
      return
   end if
!
   Fs = 0.0; Ss = 0.0 ; Rs = 0.0
   
!/* 3. Determine time zone (longitude/15).
!      Adjust detection and forecast (CMC) time from UTC to local time such that 
!      noon is at solar zenith. Adjust LDT to LST (hardcoded to LST).
!      Determine Julian dates. */
   timezone = (feps%lon) / 15.0 !// calculate timezone on the fly

   cmcLST = cmcUTC_in + timezone
   if (cmcLST < 0.0) cmcLST = cmcLST + 24.0

!/* Adjust LDT value to LST */
!// decimal hours
   detectionUTC = int(feps%dtime / 100) + mod(feps%dtime, 100) / 60.0
   detectionLST = detectionUTC - real(cffeps_ldt) + timezone

   if (detectionLST < 0.0) detectionLST = detectionLST + 24.0

!/* 5. If new fire, determine the hours from the first hourly CMC forecast
!      to the detection time: if less than 24 hours, an initial fire size
!      is calculated (based on persistence routine); if greater than zero,
!      then the fire starts at zero size. */

   if (istep == 0) then
      !// determine the initial Area(t) for first CMC hour.

             ! // hours from first CMC hour to detection time     
      dt = 24.0 * (feps%dj - cmcDj) + detectionUTC - cmcUTC_in

      if (dt < 24.0) then ! detection less than 24 hours after first CMC hour
         if ((trim(cffeps_fire_shape) == "tophat") .or. &
             (trim(cffeps_fire_shape) == "weighted")) then
!/* new approach, count backwards from detectionLST */
            thisLST = int(detectionLST)
!            rsum = weight(thisLST + 1) * (detectionLST - real(thisLST))
            i = thisLST + 1
            if (i > 23) i = i - 23
            ij = i + 1
            rsum = weight(ij) * (detectionLST - real(thisLST))

            thisLST = thisLST - 1
            if (int(cmcLST) > thisLST) then !// cmcLST on previous day
               thisLST = thisLST + 24
            end if
            do i = thisLST, int(cmcLST), -1
                !// accumulate the hourly weight over the course of a day
                ij = i + 1
                if (i > 23) ij = i - 23
                rsum = rsum + weight(ij)
            end do

            if (dt < 0) then
            !  // account for burning prior to forecast start
               estarea2 = feps%estarea - feps%estarea * rsum + &
                          float(1 - int(dt / 24.0)) * feps%estarea
            else
            !  // new value for estarea, capturing the entire burn period
               estarea2 = feps%estarea - feps%estarea * rsum
            end if

         end if

      else   !// detection 24 hours or more after first CMC hour
         estarea2 = 0.0
      end if

      estarea2 = max(0.0, estarea2)
      feps%area = estarea2
      parea = estarea2

   end if

!/* adjust cmcUTC to a time wrt detection time and date, so this is 0 at
!   detection time, negative before and positive after (can exceed 24) */
    !   // should use a new variable name like "elapsed"
   cmcUTC = cmcUTC_in + real(24 * (cmcDj - feps%Dj))

!/* elapsed is the time since detectionLST (dhrs) */
      !  // used in Brigg's model to determine the current time
!   elapsed = min(0.0, cmcUTC - detectionUTC)
!
!/* Calculate FBP values at time of detection (and at current time) */
   ws = 1.852 * met%ws   ! /* knots to km/hr */
      
   call cffeps_fbpcalc(feps%fmc, feps%bui, feps%ffmc, ifuel, ws, &
        feps%percent_conifer, feps%percent_dead_fir, feps%curing, fbp)

!/* 8. Determine discovery time (the number of hours of growth required to reach
!      the detection size).
!        When persistence is being used, this time is assumed to be 24 hours. */
   if (trim(cffeps_fire_shape) == "top-hat" .or. &
       trim(cffeps_fire_shape) == "weighted") then
      discovery = 24.0 ! // set the time of discovery equal to 24 hours
   else
!
      t1 = 0.0 
      t2 = 0.0
      A = feps%estarea
      P = 0.0
      D = 0.0
      call cffeps_procalc(ifuel, fbp, t1, t2, A, P, D)
      ! // use the detectionLST to determine discovery; afterwards use cmcLST 
      !    for the hour
      discovery = t2
   end if

!/* 9. If current time is prior to discovery, the fire has not yet occurred
!      and does not grow; else: */

      ! // difference in time between cmcUTC and detectionUTC
   dt = cmcUTC - (detectionUTC - discovery)
   if ((dt <= 0.0) .or. (discovery == 999.9))  then ! // no fire yet
      r_smoke = 0.0
      dz = 0.0
      mplume = 0.0
      growth = 0.0
      feps%area = 0.0
      feps%totalemissions = 0.0
      feps%Qo = 0.0
      feps%Qs = 0.0
      emissions%r = 0.0
      emissions%s = 0.0
      emissions%f = 0.0
      
      return
   end if
!
!/* 9.a. If the current time corresponds to the reset time (if being used, not
! the default), set the  area, cumulative energy and total emissions to zero */
   if ((cffeps_reset >= 0.0) .and. (cmcLST >= cffeps_reset) .and. &
       (cmcLST < (cffeps_reset + cffeps_timestep))) then
      parea = 0.0
      feps%Qo = 0.0
      feps%totalemissions = 0.0
   else
      parea = feps%area
   end if
!
!/* 9.b. Determine difference in time between current time and detection time. 
!        If less than an hour, calculate partial hour growth; otherwise, 
!        calculate hourly growth according to top-hat or weighted approach.  
!        Add to total area. */
            ! // this portion of the code seems to be in flux
   if (trim(cffeps_fire_shape) == "elliptical") then
      if (parea == 0.0) then
         t1 = 0
         !    // these can be multiday lengths, when grown at
         !       noon ROS produce wrong values
         t2 = 24.0 * ((feps%dj + cmcUTC / 24.0) - &
              (feps%dj + (detectionUTC - discovery) / 24.0))
         t2 = cmcUTC - (detectionUTC - discovery)

         if (t2 > 0.) then
            A = 0.0
            P = 0.0
            D = 0
            call cffeps_procalc(ifuel, fbp, t1, t2, A, P, D)
            growth = A ! // area at cmcUTC
         else
            growth = 0.0
         end if

         cmcUTCo = cmcUTC0 + 24.0 * (cmcDj0 - feps%Dj) 
         if (cmcUTCo >= 0.0) parea = feps%estarea

         growth = feps%estarea ! //temporary fix

         parea = estarea2 ! // new approach 2018/01/18
         growth = 0  ! //temporary fix
!
      else
         t1 = 0.0
         t2 = 0.0
         A = parea
         P = 0.0
         D = 0.0
         call cffeps_procalc(ifuel, fbp, t1, t2, A, P, D)

         t1 = t2
         t2 = t2 + cffeps_timestep
         A = 0.0
         P = 0.0
         D = 0.0
         call cffeps_procalc(ifuel, fbp, t1, t2, A, P, D)
         growth = A !  // area growth in one time step: 
                                  !      A(t2+cffeps_timestep)-A(t2)
      end if
   end if

   if (trim(cffeps_fire_shape) == "tophat" .or. &
       trim(cffeps_fire_shape) == "weighted") then
         ! // this is the default based on readfeps()
      if (cmcLST >= 24.0) cmcLST = cmcLST - 24.0
         ! // weighted fire growth of previous hour
      if (dt > 0.0 .and. dt < cffeps_timestep) then
         growth = dt * weight(int(cmcLST) + 1) * feps%estarea 
      else
         growth = cffeps_timestep * weight(int(cmcLST) + 1) * feps%estarea
      end if
   end if

   if (trim(cffeps_fire_shape) == "line") then
      if (parea == 0.0 .and. dt > 0.0) parea = feps%estarea
         !// diameter of a circle of estarea
      diameter = 2.0 * sqrt(10000.0 * feps%estarea / pi)

      if (dt > 0.0  .and.  dt < 1.0) then
         growth = dt * 60.0 * fbp%ROS * diameter * 1.0e-4
      else
         growth = cffeps_timestep * 60.0 * fbp%ROS * diameter * 1.0e-4
      end if
   end if

   if (istep == 0) growth = 0.0

   feps%area = growth + parea

! Set the fire perimeter ([m]) based on the (CFWIS) input area (feps%estarea) 
!/* This assumes the entire fire perimeter is generating smoke */
   if (cffeps_fire_shape(1:4) == "line") then
    ! /* for a line fire, we are assigning the perimeter value to the
    !    diameter of the area [KRA 08/07/2014] */
      perimeter = 2.0 * sqrt(feps%area * 1.0e4 / pi)
   else
   !/* assume a circular fire [m]
      perimeter = 2.0 * pi* sqrt(feps%area * 1.0e4 / pi)
   end if
   
   r_smoke = 0.0
   tsurf = met%T(1)
            
! Standard moisture content equations (and convert from percent to fraction)
   mcF = 0.0
   mcH = 0.0
   mcL = 147.2 * (101.0 - feps%ffmc) / (59.5 + feps%ffmc) * 1.0e-2
   if (feps%dmc > 0.0) &
      mcF = (exp((feps%dmc - 244.72) / (-43.43)) + 20.0) * 1.0e-2
   if (feps%dc > 0.0) &
     !note: this is actually moisture equivalent in hundreths of an inch
     ! mcH = 800./exp(feps->DC/400.) / 100.
     ! Dan Thompson's equation based on BMW's assumption that DC is saturated 
     ! at 400%
      mcH = 400.0 / exp(feps%dc / 400.0) * 1.0e-2      

!/* 9.c. Calculate energy of the fire */
!/*   Qplume is the energy injected into the plume */
   call cffeps_energy(fbp, ifuel, qplume, tsurf, feps%area, perimeter, &
                      growth, feps%fmc, mcL, mcF, mcH)
!/* 9.d. Calculate the energy released from flaming, smoldering and
!        residual combustion.
!     Calculate flaming, smoldering and residual emissions rates in tonnes/h  */
   if (ifuel > 0 .and. growth > 0.0 .and. fbp%tfc > 0.0) then
      call EmissionsCalc2(ifuel, fbp%sfc, fbp%tfc, dob_s, mcL, mcF, mcH, &
                          flaming,    smoldering,    residual, &
                          mw_flaming, mw_smoldering, mw_residual)
   else
      flaming = 0.0
      smoldering = 0.0
      residual = 0.0

      mw_flaming = 0.0
      mw_smoldering = 0.0
      mw_residual = 0.0
      dob_s = 0.0
   end if
   qplume_per_tfc = qplume /  fbp%tfc
       
!/* 9.e Distribute the water released [kg/timestep] over time
   mw0 = mws(1)
   if (trim(cffeps_fire_type) == "wet") then
      jModel = -2
      call EmissionsOverTime2(Fs, Ss, Rs, jModel, imax, dob_s, growth, &
                              mw_flaming, mw_smoldering, mw_residual,  &
                              qplume_per_tfc)
   ! // iMax drops to 1 when growth stops, need to use MAX_TIMESTEPS
      iMax = MAX_TIMESTEPS - 1
      do i = 1, iMax
         Mws(i) = Mws(i + 1) + Fs(i) + Ss(i) + Rs(i)
      end do
      Mws(iMax + 1) = Fs(iMax + 1) + Ss(iMax + 1) + Rs(iMax + 1)
      mw0 = mw0 + Mws(1)
!     mw0 = mw0 + Mws(1) * (1.0 - fbp%CFB * 0.5)  ! incomplete combustion?
   end if

   !/*an admittedly awkward way of creating hourly energy components*/
   jModel = -1
!/* 9.e. Distribute the energy over time (iMax is the extent of time the fire 
!        burn into the future in timesteps ) */
   call EmissionsOverTime2(Fs, Ss, Rs, jModel, imax, dob_s, growth,    &
                           flaming, smoldering, residual, qplume_per_tfc)
   ! // iMax drops to 1 when growth stops, need to use MAX_TIMESTEPS
   iMax = MAX_TIMESTEPS - 1 
   do i = 1, iMax
!// Overwrite the previous timesteps calculations [i+1] with the current [i]
      feps%Qs(i) = feps%Qs(i + 1) + Fs(i) + Ss(i) + Rs(i)
   end do
   feps%Qs(iMax + 1) = Fs(iMax + 1) + Ss(iMax + 1) + Rs(iMax + 1)
                                              
!/* 9.f. From the area growth and energy released, calculate the plume rise */
   qplume = feps%Qs(1)    !  // need to check this
      
   lapse_rate = -999.0
   dz = -999.0

!/* 9.f. (i) if type=dry, use all upper air data following a piecewise method
!            of calculating plume rise */
! Update the total plume energy (accounting for any previous energy)
! before plume height calculations
   feps%Qo = feps%Qo + qplume
   if (qplume <= 0.0 .or. feps%area < 0.0) then
      dz = 0.0
      mplume = 0.0
      Qbb = 0.0
   else
      if (trim(cffeps_fire_type) == "dry" .or. &
          trim(cffeps_fire_type) == "wet") then
            !// new piece-wise approach
         call cffeps_plumeCalc2(met, feps%area, feps%Qo, mw0, perimeter, &
                                dz, mplume, Qbb)
      else
!/* 9.f. (ii) follow the standard average lapse rate method outlined in 
!             Anderson et al., 2011 */
         dz8 = -999.0
         dz7 = -999.0
         dz5 = -999.0
         l8 = -999.0
         l7 = -999.0
         l5 = -999.0

         ik = 2
         iref2 = 2
         do kk = ik, met_levels
            if (met%P(kk) >= 8.5E4) then
               iref2 = kk
            else if (met%P(kk) >= 7.0E4) then
               iref3 = kk
            else if (met%P(kk) >= 5.0E4) then
               iref4 = kk
            else if (met%P(kk) <= 2.5E4) then
               iref5 = kk
               exit
            end if
         end do
         dzmax = met%Z(iref5) !// arbitrarily setting the plume top to ~250 mb
    
!/* 9.f. (ii) (1) calculate height based on surface to ~850 mb lapse */
         lapse_rate = (met%T(iref2) - met%T(1)) / (met%Z(iref2) - met%Z(1))
         l8 = lapse_rate
         !/* Call plumecalc only if the environmental lapse rate is stable 
         !   (> -9.8 oC/km),
         if (lapse_rate > -0.0098) then
            call cffeps_plumecalc(feps%area, feps%Qo, tsurf, lapse_rate, &
                                  perimeter, dz, mplume, Qbb)
            dz = min(dz, dzmax)
            dz8 = dz
         end if
!/* 9.f. (ii) (2) if recalculated height greater than 2000 m,
!                  recalculate height based on surface to ~700 mb lapse rate
!                  (if resulting height less than 2000, use average) */
         if (dz > 2000.0 .or. dz <= 0.0) then
            lapse_rate = (met%T(iref3) - met%T(1)) / (met%Z(iref3) - met%Z(1))
            l7 = lapse_rate
            if (lapse_rate > -0.0098) then
               call cffeps_plumecalc(feps%area, feps%Qo, tsurf, lapse_rate, &
                                     perimeter, dz, mplume, Qbb)
               dz = min(dz, dzmax)
               dz7 = dz
               if (dz < 2000.0) then
                  lapse_rate = (l8 + l7) * 0.5
                  if (lapse_rate > -0.0098) then
                     call cffeps_plumecalc(feps%area, feps%Qo, tsurf, &
                                           lapse_rate, perimeter, dz, &
                                           mplume, Qbb)
                     dz = min(dz, dzmax)
                  end if
               end if
            end if
!/* 9.f. (ii) (3) if recalculated height greater than 4000 m,
!                  recalculate height based on surface to ~500 mb lapse rate
!                  (if resulting height less than 4000, use average) */
            if (dz > 4000.0 .or. dz <= 0.0) then
               lapse_rate = (met%T(iref4) - met%T(1)) / &
                            (met%Z(iref4) - met%Z(1))
               l5 = lapse_rate
               if (lapse_rate > -0.0098) then
                  call cffeps_plumecalc(feps%area, feps%Qo, tsurf, lapse_rate, &
                                        perimeter, dz, mplume, Qbb)
                  dz = min(dz, dzmax)
                  dz5 = dz
                  if (dz < 2000.0) then
                     lapse_rate = (l8 + l7) * 0.5
                     if (lapse_rate > -0.0098) then
                        call cffeps_plumecalc(feps%area, feps%Qo, tsurf, &
                                              lapse_rate, perimeter, dz, &
                                              mplume, Qbb)
                        dz = min(dz, dzmax)
                     end if
                  end if
               end if
                     
!/* 9.f. (ii) (4) if superadiabatic from surface up to ~500mb, recalculate using
!                 ~850 mb as the base.
!                  recalculate height based on ~850 mb to ~700 mb lapse rate
!               (if resulting height less than 2000, use average) */
               if (dz <= 0.0) then
                  lapse_rate = (met%T(iref3) - met%T(iref2)) / &
                               (met%Z(iref3) - met%Z(iref2))
                  l7 = lapse_rate
                  if (lapse_rate > -0.0098) then
                     call cffeps_plumecalc(feps%area, feps%Qo, tsurf, &
                                           lapse_rate, perimeter, dz, &
                                           mplume, Qbb)
                     dz = min(dz, dzmax)
                     dz7 = dz
                     if (dz < 2000.0) then
                        lapse_rate = (l8 + l7) * 0.5
                        if (lapse_rate > -0.0098) then
                           call cffeps_plumecalc(feps%area, feps%Qo, tsurf, &
                                                 lapse_rate, perimeter, dz, &
                                                 mplume, Qbb)
                           dz = min(dz, dzmax)
                        end if
                     end if
                  end if
                     
!/* 9.f. (ii) (5) if recalculated height greater than 4000 m,
!                  recalculate height based on ~850 mb to ~500 mb lapse rate
!                  (if resulting height less than 4000, use average) */
                  if (dz > 4000.0 .or. dz <= 0.0) then
                     lapse_rate = (met%T(iref4) - met%T(iref2)) / &
                                  (met%Z(iref4) - met%Z(iref2))
                     l5 = lapse_rate
                     if (lapse_rate > -0.0098) then
                        call cffeps_plumecalc(feps%area, feps%Qo, tsurf, &
                                              lapse_rate, perimeter, dz, &
                                              mplume, Qbb)
                        dz = min(dz, dzmax)
                        dz5 = dz
                        if (dz < 2000.0) then
                           lapse_rate = (l8 + l7) * 0.5
                           if (lapse_rate > -0.0098) then
                              call cffeps_plumecalc(feps%area, feps%Qo, tsurf, &
                                                    lapse_rate, perimeter, dz, &
                                                    mplume, Qbb)
                              dz = min(dz, dzmax)
                           end if
                        end if
                     end if
                  end if ! if (dz > 4000.  || dz < 0.)

               end if  !if (dz < 0.)  [superadiabatic from surface]
            end if !if (dz > 4000.  || dz < 0.)
         end if !if (dz > 2000.  || dz < 0.)
         
         if (dz8 > 2000.0 .and. dz7 < 2000.0) then
            dz = (dz8 + dz7) * 0.5
         end if

         if (dz7 > 4000.0 .and. dz5 < 4000.0) then
            dz = (dz7 + dz5) * 0.5
         end if

!/* 9.f. (iii) limit height to 250 mb height */
         dz = min(dz, dzmax)
            
!/* 9.f. (iv) impose a minimum height */
         dz = max(dz, dzmin)
         
      end if
   end if
                        
!   feps%Qo = max(feps%Qo - Qbb, 0.0)
   feps%Qo = max(feps%Qo, 0.0)

!/* 9.g. Find emodel that matches the fuel type */
   jModel = 0

!/* 9.h.  Distribute the emission over time */
   call EmissionsOverTime2(Fs, Ss, Rs, jModel, imax, dob_s, growth,    &
                           flaming, smoldering, residual, qplume_per_tfc)

   ! // iMax drops to 1 when growth stops, need to use MAX_TIMESTEPS
   iMax = MAX_TIMESTEPS - 1
   do i = 1, imax
      emissions%f(i) = emissions%f(i + 1) + Fs(i) 
      emissions%s(i) = emissions%s(i + 1) + Ss(i)
      emissions%r(i) = emissions%r(i + 1) + Rs(i)
   end do
   emissions%f(imax + 1) = Fs(imax + 1)
   emissions%s(imax + 1) = Ss(imax + 1)
   emissions%r(imax + 1) = Rs(imax + 1)

!/* 9.i. Calculate total emissions and r_smoke */
      ! // in tonnes
   feps%totalemissions = feps%totalemissions + 10.0 * fbp%TFC * growth
      ! // in g/kg
   if (dz > 0.0 .and. mplume > 0.0) then
      r_smoke = 1000.0 * (1000.0 * feps%totalemissions) / mplume
   else
      r_smoke = 0.0
   end if

!/* replace missing values (-9999) or any negative plume heights with 0. */
   if (dz < 0.0) then
      dz = 0.0
      mplume = 0.0
   end if
      
   return
    
 end subroutine cffeps_calc
