!============================================================================!
!
! Projet / Project : GEM-MACH
! Fichier / File   : cffeps_fbp_mod.ftn90
! Creation         : Kerry Anderson - Jan 6, 2011
!                  : (C To Fortran)
!                    A. Akingunola, J. Chen, and P. Makar - Fall 2018
! Description      : Fire Behavior Prediction System for CFFEPS
!/* This subroutine represents equations from
!
!Wotton, B.M.; Alexander, M.E.; Taylor, S.W.  2009,.  Updates and revisions to the
!    1992 Canadian Forest Fire Behavior Prediction System .  Natural Resources
!    Canada, Canadian Forest Service, Great Lakes Forestry Centre, Sault Ste. Marie,
!    Ontario, Canada.  Infomration Report GLC-X-10, 45 p.
!
!Updates are indicated with a "- 2009" in the equation number comment on the right
!
!   Discrepancies between BMW's fbp.c and ST-X-3
!
!   eqn 32: BMW has 33.5 instead of 35.5 (see ROScalc and Slopecalc)
!   eqn 57: BMW had forced SFC to 2.0 for C6 (this is now gone)
!   b[O1b]: BMW has 0.0829 instead of 0.0310
!   c[O1a]: BMW has 1.41 instead of 1.4
!*/
!
!// Note: There is no attempt to account for greened-up deciduous (D2)
!============================================================================
!
 module cffeps_fbp_mod

   use cffeps_mod,  only: fbp_type, MAX_TIMESTEPS, LABEL_SIZE, &
                          cffeps_timestep, cffeps_fueltypes,   &
                          fuel_size, max_fuels, ifuel_c2, ifuel_d1
   
   implicit none
   private
   public  :: cffeps_fbpcalc, FMCcalc
   
   real(kind=4), parameter :: pi = 3.1415926, NoBUI = -1.0
   
   real(kind=4), dimension(max_fuels), parameter :: a = &
                    (/  90.,  110.,   110.,  110.,   30.,   30., &
                        45.,   30.,   30.,     0.,    0.,  120., &
                       100.,   75.,   40.,   55.,  190.,   250., &
                         0.,   0. /)
   real(kind=4), dimension(max_fuels), parameter :: b = &
                    (/.0649, .0282,  .0444, .0293, .0697, .0800, &
                      .0305, .0232, .0232,     0.,    0., .0572, &
                      .0404, .0297, .0438, .0829, .0310,  .0350, &
                         0.,   0.  /)
   real(kind=4), dimension(max_fuels), parameter :: c = &
                    (/  4.5,   1.5,    3.0,   1.5,   4.0,   3.0, &
                        2.0,   1.6,    1.6,    0.,    0.,   1.4, &
                       1.48,   1.3,    1.7,   3.2,   1.4,   1.7, &
                         0.,   0. /)
   real(kind=4), dimension(max_fuels), parameter :: q = &
                    (/ 0.90,  0.70,   0.75,  0.80,  0.80,  0.80, &
                       0.85,  0.90,   0.90,    .8,    .8,    .8, &
                         .8,  0.75,   0.75,  0.75,  1.00,  1.00, &
                         0.,   0.  /)
   real(kind=4), dimension(max_fuels), parameter :: BUIo = &
                    (/ 72.,   64.,   62.,    66.,   56.,   62.,  &
                      106.,   32.,   32.,    50.,   50.,   50.,  &
                       50.,   38.,   63.,    31.,    1.,    1.,  &
                        0.,    0./)
   real(kind=4), dimension(max_fuels), parameter :: CBHs = &
                    (/  2.,    3.,     8.,    4.,   18.,    7.,   &
                       10.,    0.,     0.,    6.,    6.,    6.,   &
                        6.,    0.,     0.,    0.,    0.,    0.,   &
                        0.,    0./)
   real(kind=4), dimension(max_fuels), parameter :: CFLs = &
                    (/ .75,   .80,   1.15,  1.20,  1.20,  1.80,   &
                       .50,    0.,     0.,   0.8,   0.8,   0.8,   &
                       0.8,    0.,     0.,    0.,    0.,    0.,   &
                        0.,    0./)
                        
   contains
  
!    double t,               /* Minutes since ignition */
!           ISI,             /* ISI */
!           WS,              /* wind speed [kmh] */
!           WD,              /* wind direction [degrees] */
!           GS,              /* Slope [percent] */
!           Aspect,          /* Aspect [degrees] */
!           PC,              /* Percent Confier for M1/M2 */
!           PDF,             /* Percent Dead Fir for M3/M4 */
!           Cured,           /* Percent Cured for O1a/O1b (85% default) */
!           GFL,             /* Grass Fuel Load [kg/m^2] (0.3 default) */
!           CBH,             /* Crown to Base Height [m] (FBP defaults)*/
!           CFL,             /* Crown Fuel Load [kg/m^2] (FBP defaults) */
!           FMC,             /* FMC if known */
!           SH,              /* C6 Stand Height [m] - 2009 */
!           SD,              /* C6 Stand Density [stems/ha] - 2009 */
!           theta,           /* elliptical direction of calculation */
! 
! /* outputs */
!           ROS,             /* Rate of Spread [m/min] */
!           FROS,            /* Flank rate of Spread [m/min] */
!           BROS,            /* Back Rate of Spread [m/min] */
!           CFB,             /* Crown Fraction Burned */
!           HFI,             /* Head Fire Intensity [kW/m] */
!           TFC,             /* Total Fuel Consumption [kg/m^2]  */
!           SFC,             /* Surface Fuel Consumption [kg/m^2] */
   subroutine cffeps_fbpcalc(fmc, bui, ffmc, ifuel, ws, percent_conifer, &
                             percent_dead_fir, grass_curing, fbp)
      implicit none
       
      integer(kind=4), intent(in)    :: ifuel
      real(kind=4),    intent(in)    :: fmc, ws, bui, ffmc
      real(kind=4),    intent(in)    :: percent_conifer, percent_dead_fir, grass_curing
      type(fbp_type),  intent(inout) :: fbp
      
      real(kind=4) :: sfc, tfc, cfb, ros, fros, bros, hfi
      real(kind=4) :: t, wd, gs, aspect, pc, pdf, cured, cbh, cfl, &
                      sh, sd
      
      character(len=FUEL_SIZE) :: fueltype
      real(kind=4) :: isi, lb, wsv, cfc, ff, ffc, wfc, sf, cf, m
      real(kind=4) :: bfw, bisi, rsc, raz, saz, wse, wsx, wsy, waz
      real(kind=4) :: work, zero, cent, rsz, rsf, rsf_c2, rsf_d1
      real(kind=4) :: isz, isf, isf_c2, isf_d1
!      real(kind=4) :: alpha, lbt
      
      t = 0.0
      wd = 0.0  ! * pi/180.;        /* radians */
      gs = 0.0
      aspect = 0.0
      pc = percent_conifer
      pdf = percent_dead_fir
      cured = grass_curing
      fbp%gfl = 0.35
      cbh = 7.0
      cfl = -1.0
      sh = 0.0
      sd = 0.0
    
      zero = 0.0
      
      m = 147.2 * (101.0 - ffmc) / (59.5 + ffmc)                ! /* 46 */
      ff = 91.9 * exp(-0.1386 * m) * (1.0 + (m**5.31) / 4.93e7) ! /* 45 */

      fueltype = cffeps_fueltypes(ifuel)
      
!/* presently, we do not accept a zero CBH; use near zero if necessary */
      if (cbh <= 0.0 .or. cbh > 50.0) then
         if (trim(fueltype) == "C6" .and. sd > 0.0 .and. sh > 0.0) then
            cbh = -11.2 + 1.06 * sh + 0.00170 * sd           !  /* 91 */
            cbh = max(0.0, cbh)
         else
            cbh = CBHs(ifuel)
         end if
      end if
      
!/* presently, we do not accept a zero CFL,; use near zero if necessary */
      if (cfl <= 0.0 .or. cfl > 2.0) cfl = CFLs(ifuel)
!
!****************************************************************************** 
!/* Surface Fuel Consumption (SFC) calculation */ - SFCcalc
!
      select case (trim(fueltype))
       case ("C1")
!//       sfc = 1.5 * (1. - exp(-0.230 * (ffmc - 81.0)))     ! /* 9 */
          if (ffmc > 84.0) then                              ! /* 9a - 2009 */
             sfc = 0.75 + 0.75 * sqrt(1.0 - exp(-0.23 * (ffmc - 84.0)))
          else                                               ! /* 9b - 2009 */
             sfc = 0.75 - 0.75 * sqrt(1.0 - exp(-0.23 * (84.0 - ffmc)))
          end if

       case ("C2", "M3", "M4")
          sfc = 5.0 * (1.0 - exp(-0.0115 * bui))             ! /* 10 */

       case ("C3", "C4")
          sfc = 5.0 * (1.0 - exp(-0.0164 * bui))**2.24       ! /* 11 */

       case ("C5", "C6")
          sfc = 5.0 * (1.0 - exp(-0.0149 * bui))**2.48       ! /* 12 */

       case ("C7")
          if (ffmc > 70.0) then
             ffc = 2.0 * (1.0 - exp(-0.104 * (ffmc - 70.0))) ! /* 13 */
          else
             ffc = 0.0
          end if
          wfc = 1.5 * (1.0 - exp(-0.0201 * bui))             ! /* 14 */
          sfc = ffc + wfc                                    ! /* 15 */

       case ("D1")
          sfc = 1.5 * (1.0 - exp(-0.0183 * bui))             ! /* 16 */

       case ("M1", "M2")
          ffc = pc * 1.0e-2 * (5.0 * (1.0 - exp(-0.0115 * bui)))
          wfc = (100.0 - pc) * 1.0e-2 * (1.5 * (1.0 - exp(-0.0183 * bui)))
          sfc = ffc + wfc                                    ! /* 17 */

       case ("O1a", "O1b")
          sfc = fbp%gfl                                          ! /* 18 */

       case ("S1")
          ffc = 4.0 * (1.0 - exp(-0.025 * bui))              ! /* 19 */
          wfc = 4.0 * (1.0 - exp(-0.034 * bui))              ! /* 20 */
          sfc = ffc + wfc                                    ! /* 25 */

       case ("S2")
          ffc = 10.0 * (1.0 - exp(-0.013 * bui))             ! /* 19 */
          wfc = 6.0 * (1.0 - exp(-0.060 * bui))              ! /* 20 */
          sfc = ffc + wfc                                    ! /* 25 */

       case ("S3")
          ffc = 12.0 * (1.0 - exp(-0.0166 * bui))            ! /* 19 */
          wfc = 20.0 * (1.0 - exp(-0.0210 * bui))            ! /* 20 */
          sfc = ffc + wfc                                    ! /* 25 */
       case default
          sfc = -1.0
      end select

      sfc = max(0.000001, sfc)
!
!/* Corrections to reorient WAZ, SAZ */
      waz = wd + pi
      if (waz > 2.0 * pi) waz = waz - 2.0 * pi
      if (gs > 0.0 .and. ffmc > 0.) then
!/* nb: BMW's data set appears to have aspect not saz */
         saz = aspect + pi
         if (saz > 2.0 * pi) saz = saz - 2.0 * pi
!****************************************************************************** 
!/* Effect of Slope on Rate of Spread */ - slopecalc
!
         if (gs >= 70.0) then
            sf = 10.0
         else
            sf = exp(3.533 * (gs * 1.0e-2)**1.2)          !  /* 39 */
         end if
         isz = ISIcalc(ff, zero)
         rsz = ROScalc(ifuel, isz, NoBUI, fmc, sfc, pc, pdf, cured, cbh)
         rsf = rsz * sf                                   !  /* 40 */
         
         select case (trim(fueltype))
           case ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "D1", "S1", &
                 "S2", "S3")
              isz = ISIcalc(ff, zero)
              rsz = ROScalc(ifuel, isz, NoBUI, fmc, sfc, pc, pdf, cured, cbh)
              rsf = rsz * sf                                   !  /* 40 */
              work = max(0.01, 1.0 - (rsf / a(ifuel))**(1.0 / c(ifuel)))
              isf = log(work) / (-b(ifuel))           ! /* 41(a,b) - 2009 */
           case ("M1", "M2")
              !ifuel_c2 = findloc(cffeps_fueltypes, "C2")
!              ifuel_c2 = maxloc(merge(1, 0, trim(cffeps_fueltypes) == "C2"), &
!                                dim = 1)
              rsz = ROScalc(ifuel_c2, isz, NoBUI, fmc, sfc, pc, pdf, cured, cbh)
              rsf_c2 = rsz * sf                           ! /* 40 */ 
              !ifuel_d1 = findloc(cffeps_fueltypes, "D1")
!              ifuel_d1 = maxloc(merge(1, 0, trim(cffeps_fueltypes) == "D1"), &
!                                dim = 1)
              rsz = ROScalc(ifuel_d1, isz, NoBUI, fmc, sfc, pc, pdf, cured, cbh)
              rsf_d1 = rsz * sf                           ! /* 40 */
              
              work = max(0.01, 1.0 - (rsf_c2 / a(ifuel_c2))**(1.0 / c(ifuel_c2)))
              isf_c2 = log(work) / (-b(ifuel_c2))         ! /* 41(a,b) - 2009 */
              work = max(0.01, 1.0 - (rsf_d1 / a(ifuel_d1))**(1.0 / c(ifuel_d1)))
              isf_d1 = log(work) / (-b(ifuel_d1))         ! /* 41(a,b) - 2009 */
              
              isf = pc * 1.0e-2 * isf_c2 + (1.0 - pc * 1.0e-2) * isf_d1 
                                                          ! /* 42a - 2009 */
           case ("M3", "M4")
              cent = 100.0
              rsz = ROScalc(ifuel, isz, NoBUI, fmc, sfc, pc, cent, cured, cbh)
              rsf = rsz * sf                              ! /* 40 */ 
!              ifuel_d1 = maxloc(merge(1, 0, cffeps_fueltypes == "D1  "), &
!                                dim = 1)
              rsz = ROScalc(ifuel_d1, isz, NoBUI, fmc, sfc, pc, pdf, cured, cbh)
              rsf_d1 = rsz * sf                           ! /* 40 */
              
              work = max(0.01, 1.0 - (rsf / a(ifuel))** (1.0 / c(ifuel)))
              isf = log(work) / (-b(ifuel))               ! /* 41(a,b) - 2009 */
              work = max(0.01, 1.0 - (rsf_d1 / a(ifuel_d1))**(1.0 / c(ifuel_d1)))
              isf_d1 = log(work) / (-b(ifuel_d1))         ! /* 41(a,b) - 2009 */
              
              isf = pdf * 1.0e-2 * isf + (1.0 - pdf * 1.0e-2) * isf_d1 
                                                          ! /* 42a - 2009 */
           case ("O1a", "O1b")
              if (cured < 58.8) then
                 cf = 0.005 * (exp(0.061 * cured) - 1.0)  ! /* 35a - 2009 */
              else
                 cf = 0.176 + 0.02 * (cured - 58.8)       ! /* 35b - 2009 */
              end if

              isz = ISIcalc(ff, zero)
              rsz = ROScalc(ifuel, isz, NoBUI, fmc, sfc, pc, pdf, cured, cbh)
              rsf = rsz * sf                             ! /* 40 */
              work = max(0.01, 1.0 - (rsf / (cf * a(ifuel)))**(1.0 / c(ifuel)))
              isf = log(work) / (-b(ifuel))              ! /* 43(a,b) - 2009 */
         end select
         
!//       WSE = log(ISF/(0.208 * fF))/0.05039                       ! /* 44 */

         wse = 1.0 / 0.05039 * log(isf / (0.208 * ff))  ! /* 44a , 44d- 2009 */
         if (wse > 40.0) then                           ! /* 44e - 2009 */
            if (isf < (0.999 * 2.496 * ff)) then
               wse = 28.0 - (1.0 / 0.0818 * log(1.0 - isf / (2.496 * ff)))
                                                        ! /* 44b - 2009 */
            else
               wse = 112.45                             ! /* 44c - 2009 */
            end if
         end if
         
         wsx = ws * sin(waz) + wse * sin(saz)           ! /* 47 */
         wsy = ws * cos(waz) + wse * cos(saz)           ! /* 48 */
         
         wsv = sqrt(wsx * wsx + wsy * wsy)              ! /* 49 */
         raz = acos(wsy / wsv) !   /* in radians */       /* 50 */
         if (wsx < 0.0) raz = 2.0 * pi - raz            ! /* 51 */
      else
         wsv = ws
         raz = waz
      end if
!
!****************************************************************************** 
   
      isi = ISIcalc(ff, wsv)
!
!******************************************************************************
! Calculate CFB and ROS
      if (trim(fueltype) == "C6") then
         ! /* We use C6calc to calculate CFB */
         call C6calc(ifuel, isi, bui, fmc, sfc, cbh,  ros, cfb, rsc)
      else
         ros = ROScalc(ifuel, isi, bui, fmc, sfc, pc, pdf, cured, cbh)
         if (cfl > 0.0) then
            cfb = CFBcalc(fmc, sfc, ros, cbh)
         else
            cfb = 0.0
         end if
      end if
!
!******************************************************************************
!** LBcalc
      if (fueltype(1:2) == "O1") then
         if (wsv >= 1.0) then
            lb = 1.1 * wsv**0.464 !/* corrected from "+" to "*" in the errata; 80 */
         else
            lb = 1.0                                               ! /* 81 */
         end if
      else
         lb = 1.0 + 8.729 * (1.0 - exp(-0.030 * wsv))**2.155       ! /* 79 */
      end if
!
!******************************************************************************
!** BROScalc      
      bfw  = exp(-0.05039 * wsv)                                   ! /* 75 */
      bisi = 0.208 * bfw * ff                                      ! /* 76 */
!/* Note the BUI effect is captured in ROScalc */
      bros = ROScalc(ifuel, bisi, bui, fmc, sfc, pc, pdf, cured, cbh) ! /* 77 */
      fros = (ros + bros) * 0.5 / lb                               ! /* 89 */

!******************************************************************************
! Calculate TFC
      cfc = cfl * cfb
      select case (trim(fueltype))
         case ("M1", "M2")
            cfc = pc * 1.0e-2 * cfc
         case ("M3", "M4")
            cfc = pdf * 1.0e-2 * cfc
      end select
      tfc = sfc + cfc

!******************************************************************************
! Calculate HFI
      hfi = 300.0 * tfc * ros
      
!*** LBtcalc      
!*      if (accel) then
!*         lbt = lb
!*      else if (t > 0.0) then
!*         select case (trim(fueltype))
!*           case ("C1", "O1a", "O1b", "S1", "S2", "S3")
!*              alpha = 0.115                                  !  /* page 41 */
!*           case default
!*              alpha = 0.115 - 18.8 * (cfb**2.5) * exp(-8.0 * cfb)  !  /* 72 */
!*         end select
!*         lbt = (lb - 1.0) * (1.0 - exp(-alpha * t)) + 1.0    ! /* 81 - 2009 */
!*      else
!*         lbt = 1.0      
!*      end if

      fbp%cfb  = cfb
      fbp%ros  = ros
      fbp%fros = fros
      fbp%bros = bros
      fbp%tfc  = tfc
      fbp%sfc  = sfc
      fbp%hfi  = hfi
      
      return
   end subroutine cffeps_fbpcalc
   
!****************************************************************************** 
!/* Foliar Moisture Content (FMC) calculation - FMCcalc
!   Note that 0.5 is added before the integer conversion in equations 2 and 4
!   Note that equations 1 and 3 use positive longitude values for Canada */
!
!    int    Dj,              /* Julian Day */
!           D0,              /* Julian day of minimum FMC */
!    double ELEV,            /* Elevation [m ASL] */
!           LAT,             /* Latitude [decimal degrees] */
!           LON,             /* Longitude [decimal degrees] */
   real(kind=4) function FMCcalc(dj, lat, lon, elev)
      implicit none
      integer(kind=4), intent(in) :: dj
      real(kind=4),    intent(in) :: lat, lon, elev
            
      integer(kind=4) :: d0, nd
      real(kind=4)    :: latn, fmc 
!
!/* Make LON positive for the Western Hemisphere */
      fmc = -1.0
         
!/* Calculate d0, date of min FMC (assuming it is not provided) */
      if (elev <= 0.0) then
         latn = 46.0 + 23.4 * exp(-0.0360 *(150. + lon))      ! /* 1 */
         d0 = int(151.0 * lat / latn + 0.5)                   ! /* 2 (+0.5) */
      else
         latn = 43.0 + 33.7 * exp(-0.0351 * (150.0 + lon))    ! /* 3 */
         d0 = int(142.1 * lat / latn + (0.0172 * elev) + 0.5) ! /* 4 (+0.5) */
      end if

      nd = abs(dj - d0)                                          ! /* 5 */

      if (nd < 30) then
         fmc = 85.0 + 0.0189 * nd * nd                           ! /* 6 */
      else if (nd < 50) then
         fmc = 32.9 + 3.17 * nd - 0.0288 * nd * nd               ! /* 7 */
      else
         fmc = 120.0                                             ! /* 8 */
      end if
!
      FMCcalc = fmc
      
      return
   end function FMCcalc
!****************************************************************************** 

!****************************************************************************** 
   real(kind=4) function ISIcalc(ff, wsv)
      implicit none
            
      real(kind=4), intent(in)  :: ff, wsv

      real(kind=4) :: fw

         if (wsv < 40.0) then
            fw = exp(0.05039 * wsv)                                ! /* 53 */
         else
            fw = 12.0 * (1.0 - exp(-0.0818 * (wsv - 28.0)))        ! /* 53a */
         end if
         
         isicalc = 0.208 * fw * ff                                 ! /* 52 */
      
      return
   end function ISIcalc
!****************************************************************************** 

!****************************************************************************** 
   subroutine C6calc(ifuel, isi, bui, fmc, sfc, cbh, ros, cfb, rsc)
      implicit none
            
      integer(kind=4), intent(in)  :: ifuel
      real(kind=4),    intent(in)  :: isi, bui, fmc, sfc, cbh
      real(kind=4),    intent(out) :: ros, cfb, rsc

      real(kind=4) :: t, h, fme, rsi, rss, fme_avg, be

      fme_avg = 0.778                                ! /* page 37 */
      t = 1500.0 - 2.75 * fmc                        ! /* 59 */
      h = 460.0 + 25.9 * fmc                         ! /* 60 */
      fme = (1.5 - 0.00275 * fmc)**4 / (460.0 + 25.9 * fmc) * 1000.0 ! /* 61 */
      rsi = 30.0 * (1.0 - exp(-0.08 * isi))**3                       ! /* 62 */
      !BEcalc
      if (bui > 0.0 .and. BUIo(ifuel) > 0.0) then
         be = exp(50.0 * log(q(ifuel)) * (1.0 / bui - 1.0 / BUIo(ifuel)))
                                                                     ! /* 54 */
      else
         be = 1.0
      end if
      rss = rsi * be                                                 ! /* 63 */
      rsc = 60.0 * (1.0 - exp(-0.0497 * isi)) * fme / fme_avg        ! /* 64 */

      if (rsc > rss) then
         cfb = CFBcalc(fmc, sfc, rss, cbh)
         ros = rss + (cfb) * (rsc - rss)                             ! /* 65 */
      else
         cfb = 0.0
         ros = rss
      end if
      
      return
   end subroutine C6calc
   
!****************************************************************************** 
!/* Crown Fraction Burned (CFB) calculation */
   real(kind=4) function CFBcalc(fmc, sfc, ros, cbh)
      implicit none
            
      real(kind=4),  intent(in)  :: fmc, sfc, ros, cbh
      
      real(kind=4) :: csi, rso
      
      CFBcalc = 0.0
      csi = 0.001 * (cbh**1.5) * (460.0 + 25.9 * fmc)**1.5    ! /* 56 */
      rso = csi / (300.0 * sfc)                               ! /* 57 */
      if (ros > rso) CFBcalc = 1.0 - exp(-0.23 * (ros - rso)) ! /* 58 */

      return
   end function CFBcalc
   
!****************************************************************************** 
!/* Rate of Spread calculations */
!
   recursive function ROScalc(ifuel, isi, bui, fmc, sfc, pc, pdf, cured, &
                              cbh) result(ros)
      implicit none
            
      integer(kind=4), intent(in)  :: ifuel
      real(kind=4),  intent(in)    :: isi, bui, fmc, sfc, pc, pdf, cured, cbh
      
      real(kind=4) :: rsi, rsi_m34, cf, be, ros, cfb, rsc
      
      rsi = -1.0
      
!/*Note that only preliminary RSS calculations are done for C6 in this routine*/
      select case (trim(cffeps_fueltypes(ifuel)))
        case ("C1", "C2", "C3", "C4", "C5", "C7", "D1", "S1", "S2", "S3")
          rsi = a(ifuel) * (1.0 - exp(-b(ifuel) * isi))**c(ifuel)  !  /* 26 */
        case ("M1")
          rsi =       pc * 1.0e-2 * ROScalc(ifuel_c2, isi, NoBUI, fmc, sfc, &
                                            pc, pdf, cured, cbh) +          &
                (100.0 - pc) * 1.0e-2 * ROScalc(ifuel_d1, isi, NoBUI, fmc, sfc, &
                                                pc, pdf, cured, cbh)     ! /* 27 */
        case ("M2")
          rsi =       pc * 1.0e-2 * ROScalc(ifuel_c2, isi, NoBUI, fmc, sfc, &
                                            pc, pdf, cured, cbh) +          &
                0.2 * (100.0 - pc) * 1.0e-2 * ROScalc(ifuel_d1, isi, NoBUI, fmc,&
                                                sfc, pc, pdf, cured, cbh) ! /* 28 */
        case ("M3")
          rsi_m34 = a(ifuel) * (1.0 - exp(-b(ifuel) * isi))**c(ifuel) 
                                                            ! /* 30 - 2009 */
          rsi = pdf * 1.0e-2 * rsi_m34 + &
                (1.0 - pdf * 1.0e-2) * ROScalc(ifuel_d1, isi, NoBUI, fmc, sfc, &
                                                pc, pdf, cured, cbh) ! /* 29 - 2009 */
        case ("M4")
          rsi_m34 = a(ifuel) * (1.0 - exp(-b(ifuel) * isi))**c(ifuel) 
                                                            ! /* 32 - 2009 */
          rsi = pdf * 1.0e-2 * rsi_m34 + &
                0.2 * (1.0 - pdf * 1.0e-2) * ROScalc(ifuel_d1, isi, NoBUI, fmc,&
                                            sfc, pc, pdf, cured, cbh) ! /* 29 - 2009 */
        case ("O1a", "O1b")
          if (cured < 58.8) then
             cf = 0.005 * (exp(0.061 * cured) - 1.0)            ! /* 35a - 2009 */
          else
             cf = 0.176 + 0.02 * (cured - 58.8)                 ! /* 35b - 2009 */
          end if
!/* RSI has been substituted for ROS in eqn 36 */
          rsi = a(ifuel) * ((1.0 - exp(-b(ifuel) * isi))**c(ifuel)) * cf 
                                                            ! /* 36 */
      end select
      
      if (trim(cffeps_fueltypes(ifuel)) == "C6") then
         call C6calc(ifuel, isi, bui, fmc, sfc, cbh, ros, cfb, rsc)
                                !/* included here for completeness */
      else
         !BEcalc
         if (bui > 0.0 .and. BUIo(ifuel) > 0.0) then
            be = exp(50.0 * log(q(ifuel)) * (1.0 / bui - 1.0 / BUIo(ifuel)))
                                                                  ! /* 54 */
         else
            be = 1.0
         end if
         ros = be * rsi
      end if
      
      ros = max(0.000001, ros)
      
      return
   end function ROScalc
   
end module cffeps_fbp_mod
