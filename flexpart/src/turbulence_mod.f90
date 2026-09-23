  !*****************************************************************************
  !                                                                            *
  ! 2021 L. Bakels: This module contains all turbulence related subroutines    *
  ! 2023 PS: include psih, psim into this module
  !                                                                            *
  !*****************************************************************************

module turbulence_mod
  use par_mod
  use com_mod
  use particle_mod
  use pbl_profile_mod

  implicit none

  type :: turbulence_thread_state
    real :: ust,wst,ol,h,zeta,sigu,sigv,tlu,tlv,tlw
    real :: sigw,dsigwdz,dsigw2dz
  end type turbulence_thread_state

  ! GCC implements each separate THREADPRIVATE scalar through an emulated TLS
  ! lookup on macOS. Keep the same per-thread semantics while paying for one
  ! state lookup instead of a lookup for every scalar expression.
  type(turbulence_thread_state) :: turb_state
!$OMP THREADPRIVATE(turb_state)

contains

subroutine turbulence_pbl(ipart,nrand,dt,zts,rhoa,rhograd,thread)
  
  use cbl_mod
  
  implicit none 

  integer, intent(in) ::   &
    ipart,                 & ! particle index
    thread                   ! number of the omp thread
  integer, intent(inout) ::&
    nrand                    ! random number used for turbulence
  real,intent(in) ::       &
    dt,                    & ! real(ldt)
    rhoa,                  & ! air density, used in CBL
    rhograd                  ! vertical gradient of the air density, used in CBL
  real,intent(inout) ::    &
    zts                      ! local 'real' copy of the particle position
  real ::                     &
    delz,                     & ! change in vertical position due to turbulence
    ru,rv,rw,wp,icbt_r,       & ! used for computing turbulence
    dtf,rhoaux,dtftlw,ath,bth,& ! CBL related
    ptot_lhh,Q_lhh,phi_lhh,   & ! CBL related
    old_wp_buf                  ! CBL related
  integer ::                  &
    flagrein,                 & ! flag used in CBL scheme
    i                           ! loop variable
  integer(kind=2) :: icbt

  ! turb_state%tlw,turb_state%dsigwdz and turb_state%dsigw2dz are defined in hanna
    if (turbswitch) then
      call hanna(zts)
    else
      call hanna1(zts)
    endif

  !*****************************************
  ! Determine the new diffusivity velocities
  !*****************************************

  ! Horizontal components
  !**********************
    if (nrand+1.gt.maxrand) nrand=1
    if (dt/turb_state%tlu.lt..5) then
      part(ipart)%turbvel%u=(1.-dt/turb_state%tlu)*part(ipart)%turbvel%u+rannumb(nrand)*turb_state%sigu*sqrt(2.*dt/turb_state%tlu)
    else
      ru=exp(-dt/turb_state%tlu)
      part(ipart)%turbvel%u=ru*part(ipart)%turbvel%u+rannumb(nrand)*turb_state%sigu*sqrt(1.-ru**2)
    endif
    if (dt/turb_state%tlv.lt..5) then
      part(ipart)%turbvel%v=(1.-dt/turb_state%tlv)*part(ipart)%turbvel%v+rannumb(nrand+1)*turb_state%sigv*sqrt(2.*dt/turb_state%tlv)
    else
      rv=exp(-dt/turb_state%tlv)
      part(ipart)%turbvel%v=rv*part(ipart)%turbvel%v+rannumb(nrand+1)*turb_state%sigv*sqrt(1.-rv**2)
    endif
    nrand=nrand+2


    if (nrand+ifine.gt.maxrand) nrand=1
    rhoaux=rhograd/rhoa
    dtf=dt*fine

    dtftlw=dtf/turb_state%tlw

  ! Loop over ifine short time steps for vertical component
  !********************************************************
    wp=part(ipart)%turbvel%w
    icbt=part(ipart)%icbt
    do i=1,ifine
      icbt_r=real(icbt)
  ! Determine the drift velocity and density correction velocity
  !*************************************************************
      
      if (turbswitch) then
        if (dtftlw.lt..5) then
  !*************************************************************
  !************** CBL options added by mc see routine cblf90 ***
          ! LB needs to be checked if this works with openmp
          if (cblflag.eq.1) then  !modified by mc
            if (-turb_state%h/turb_state%ol.gt.5) then  !modified by mc
              flagrein=0
              nrand=nrand+1
              old_wp_buf=wp
              call cbl(wp,zts,turb_state%wst,turb_state%h,rhoa,rhograd, &
                turb_state%sigw,turb_state%dsigwdz,turb_state%tlw, &
                ptot_lhh,Q_lhh,phi_lhh,ath,bth,turb_state%ol,flagrein)
              wp=(wp+ath*dtf+&
                bth*rannumb(nrand)*sqrt(dtf))*icbt_r
              delz=wp*dtf
              if ((flagrein.eq.1).or.(wp.ne.wp).or.((wp-1.).eq.wp)) then
                call reinit_particle(zts,turb_state%wst,turb_state%h,turb_state%sigw,old_wp_buf,nrand,turb_state%ol)
                wp=old_wp_buf
                delz=wp*dtf
                nan_count(thread+1)=nan_count(thread+1)+1
              end if             
            else 
              nrand=nrand+1
              old_wp_buf=wp
              ath=-wp/turb_state%tlw+ &
                turb_state%sigw*turb_state%dsigwdz+ &
                wp*wp/turb_state%sigw*turb_state%dsigwdz+ &
                turb_state%sigw*turb_state%sigw/rhoa*rhograd
                                                                                  !2-but since ldirect =-1 for inverse time and this must be calculated for (-wp) and
                                                                                  !3-the gaussian pdf is symmetric (i.e. pdf(w)=pdf(-w) ldirect can be discarded
              bth=turb_state%sigw*rannumb(nrand)*sqrt(2.*dtftlw)
              wp=(wp+ath*dtf+bth)*icbt_r  
              delz=wp*dtf
              if ((wp.ne.wp).or.((wp-1.).eq.wp)) then ! Catch infinity or NaN
                nrand=nrand+1                      
                wp=turb_state%sigw*rannumb(nrand)
                delz=wp*dtf
                nan_count(thread+1)=nan_count(thread+1)+1
              end if
            end if
  !******************** END CBL option *******************************            
  !*******************************************************************            
          else
               wp=((1.-dtftlw)*wp+rannumb(nrand+i)*sqrt(2.*dtftlw) &
               +dtf*(turb_state%dsigwdz+rhoaux*turb_state%sigw))*icbt_r
               delz=wp*turb_state%sigw*dtf
          end if
        else
          rw=exp(-dtftlw)
          wp=(rw*wp+rannumb(nrand+i)*sqrt(1.-rw**2) &
               +turb_state%tlw*(1.-rw)*(turb_state%dsigwdz+rhoaux*turb_state%sigw))*icbt_r
          delz=wp*turb_state%sigw*dtf
        endif
        
      else
        rw=exp(-dtftlw)
        wp=(rw*wp+rannumb(nrand+i)*sqrt(1.-rw**2)*turb_state%sigw &
             +turb_state%tlw*(1.-rw)*(turb_state%dsigw2dz+rhoaux*turb_state%sigw**2))*icbt_r
        delz=wp*dtf
      endif

  !****************************************************
  ! Compute turbulent vertical displacement of particle
  !****************************************************

      if (abs(delz).gt.turb_state%h) delz=mod(delz,turb_state%h)

  ! Determine if particle transfers to a "forbidden state" below the ground
  ! or above the mixing height
  !************************************************************************

      if (delz.lt.-zts) then         ! reflection at ground
        icbt=-1
        call set_z(ipart,-zts-delz)
      else if (delz.gt.(turb_state%h-zts)) then ! reflection at turb_state%h
        icbt=-1
        call set_z(ipart,-zts-delz+2.*turb_state%h)
      else                         ! no reflection
        icbt=1
        call set_z(ipart,zts+delz)
      endif

      if (i.ne.ifine) then
        turb_state%zeta=zts/turb_state%h
        call hanna_short(zts)
      endif
      zts=real(part(ipart)%z)
    end do
    part(ipart)%turbvel%w=wp
    part(ipart)%icbt=icbt
    if (cblflag.ne.1) nrand=nrand+i
end subroutine turbulence_pbl

subroutine turbulence_above_pbl(dt,nrand,ux,vy,wp,tropop,zts)

  implicit none
  
  integer, intent(inout) ::       &
    nrand                           ! random number used for turbulence
  real, intent(inout) ::          &
    ux,vy,wp                        ! random turbulent velocities above PBL
  real, intent(in) ::             &
    tropop,                       & ! height of troposphere
    zts,                          & ! height of particle
    dt                              ! real(ldt)
  real ::                         &
    uxscale,wpscale,              & ! factor used in calculating turbulent perturbations above PBL
    weight                          ! transition above the tropopause

  if (zts.lt.tropop) then  ! in the troposphere
    uxscale=sqrt(2.*d_trop/dt)
    if (nrand+1.gt.maxrand) nrand=1
    ux=rannumb(nrand)*uxscale
    vy=rannumb(nrand+1)*uxscale
    nrand=nrand+2
    wp=0.
  else if (zts.lt.tropop+1000.) then     ! just above the tropopause: make transition
    weight=(zts-tropop)/1000.
    uxscale=sqrt(2.*d_trop/dt*(1.-weight))
    if (nrand+2.gt.maxrand) nrand=1
    ux=rannumb(nrand)*uxscale
    vy=rannumb(nrand+1)*uxscale
    wpscale=sqrt(2.*d_strat/dt*weight)
    wp=rannumb(nrand+2)*wpscale+d_strat/1000.
    nrand=nrand+3
  else                 ! in the stratosphere
    if (nrand.gt.maxrand) nrand=1
    ux=0.
    vy=0.
    wpscale=sqrt(2.*d_strat/dt)
    wp=rannumb(nrand)*wpscale
    nrand=nrand+1
  endif
end subroutine turbulence_above_pbl

subroutine turbulence_mesoscale(nrand,dxsave,dysave,ipart,usig,vsig,wsig,wsigeta,eps_eta)
  
  implicit none

  integer, intent(inout) ::       &
    nrand                           ! random number used for turbulence
  integer, intent(in) ::          &
    ipart                              ! particle index
  real, intent(in) ::             &
    eps_eta,usig,vsig,wsig,wsigeta
  real, intent(inout) ::          &
    dxsave,dysave                   ! accumulated displacement in long and lat
  real ::                         &
    r,rs                            ! mesoscale related

  r=exp(-2.*real(abs(lsynctime))/real(lwindinterv))
  rs=sqrt(1.-r**2)
  if (nrand+2.gt.maxrand) nrand=1
  part(ipart)%mesovel%u=r*part(ipart)%mesovel%u+rs*rannumb(nrand)*usig*fturbmeso
  part(ipart)%mesovel%v=r*part(ipart)%mesovel%v+rs*rannumb(nrand+1)*vsig*fturbmeso
  dxsave=dxsave+part(ipart)%mesovel%u*real(lsynctime)
  dysave=dysave+part(ipart)%mesovel%v*real(lsynctime)

#ifdef ETA
  part(ipart)%mesovel%w=r*part(ipart)%mesovel%w+rs*rannumb(nrand+2)*wsigeta*fturbmeso
  call update_zeta(ipart,part(ipart)%mesovel%w*real(lsynctime))
  if (part(ipart)%zeta.ge.1.) call set_zeta(ipart,1.-(part(ipart)%zeta-1.))
  if (part(ipart)%zeta.eq.1.) call update_zeta(ipart,-eps_eta)

#else
  part(ipart)%mesovel%w=r*part(ipart)%mesovel%w+rs*rannumb(nrand+2)*wsig*fturbmeso
  call update_z(ipart,part(ipart)%mesovel%w*real(lsynctime))
  if (part(ipart)%z.lt.0.) call set_z(ipart,-1.*part(ipart)%z)    ! if particle below ground -> refletion
#endif
end subroutine turbulence_mesoscale

subroutine hanna(z)
  !                 i
  !*****************************************************************************
  !                                                                            *
  !   Computation of \sigma_i and \tau_L based on the scheme of Hanna (1982)   *
  !   Source: 'Atmospheric Turbulence and Air Polution', chapter 4 and 7,      *
  !   J.A. Businger, edited by F.T.M. Nieuwstadt and H. van Dop                *            *
  !                                                                            *
  !   Author: A. Stohl                                                         *
  !                                                                            *
  !   4 December 1997                                                          *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! turb_state%dsigwdz [1/s]     vertical gradient of turb_state%sigw                                *
  ! turb_state%ol [m]            Obukhov length                                           *
  ! turb_state%sigu, turb_state%sigv, turb_state%sigw  standard deviations of turbulent velocity fluctuations   *
  ! turb_state%tlu [s]           Lagrangian time scale for the along wind component.      *
  ! turb_state%tlv [s]           Lagrangian time scale for the cross wind component.      *
  ! turb_state%tlw [s]           Lagrangian time scale for the vertical wind component.   *
  ! turb_state%ust, ustar [m/s]  friction velocity                                        *
  ! turb_state%wst, wstar [m/s]  convective velocity scale                                *
  !                                                                            *
  !*****************************************************************************

  implicit none

  real :: corr,z


  !**********************
  ! 1. Neutral conditions
  !**********************


  ! The addition of 1.e-2 in turb_state%sigu,turb_state%sigv,turb_state%sigw comes from ???

  if (turb_state%h/abs(turb_state%ol).lt.1.) then
    turb_state%ust=max(1.e-4,turb_state%ust)
    corr=z/turb_state%ust

    ! Eq. 7.25 Hanna 1982: turb_state%sigu/turb_state%ust=2.0*exp(-3*f*z/turb_state%ust),
    ! where f, the Coriolis parameter, is set to 1e-4
    turb_state%sigu=1.e-2+2.0*turb_state%ust*exp(-3.e-4*corr)

    ! Eq. 7.26 Hanna 1982: turb_state%sigv/turb_state%ust=turb_state%sigw/turb_state%ust=1.3*exp(-2*f*z/turb_state%ust),
    ! where f, the Coriolis parameter, is set to 1e-4
    turb_state%sigw=1.3*turb_state%ust*exp(-2.e-4*corr)

    ! ???      
    turb_state%dsigwdz=-2.e-4*turb_state%sigw
    turb_state%sigw=turb_state%sigw+1.e-2
    turb_state%sigv=turb_state%sigw

    ! Eq.7.27 Hanna 1982: TL=0.5*z/turb_state%sigw/(1+15*f*z/turb_state%ust) assumed to be valid
    ! for all three components
    turb_state%tlu=0.5*z/turb_state%sigw/(1.+1.5e-3*corr)
    turb_state%tlv=turb_state%tlu
    turb_state%tlw=turb_state%tlu


  !***********************
  ! 2. Unstable conditions
  !***********************

  else if (turb_state%ol.lt.0.) then


  ! Determine sigmas
  !*****************

    ! Eq. 4.15 Caughey 1982
    turb_state%sigu=1.e-2+turb_state%ust*(12.-0.5*turb_state%h/turb_state%ol)**0.33333
    turb_state%sigv=turb_state%sigu

    ! Ryall & Maryon 1998
    turb_state%sigw=sqrt(1.2*turb_state%wst**2*(1.-.9*turb_state%zeta)*turb_state%zeta**0.66666+ &
         (1.8-1.4*turb_state%zeta)*turb_state%ust**2)+1.e-2
    ! ???
    turb_state%dsigwdz=0.5/turb_state%sigw/turb_state%h*(-1.4*turb_state%ust**2+turb_state%wst**2* &
         (0.8*max(turb_state%zeta,1.e-3)**(-.33333)-1.8*turb_state%zeta**0.66666))


  ! Determine average Lagrangian time scale
  !****************************************

    ! Eq. 7.17 Hanna  1982
    turb_state%tlu=0.15*turb_state%h/turb_state%sigu
    turb_state%tlv=turb_state%tlu
    if (z.lt.abs(turb_state%ol)) then
      turb_state%tlw=0.1*z/(turb_state%sigw*(0.55-0.38*abs(z/turb_state%ol)))
    else if (turb_state%zeta.lt.0.1) then
      turb_state%tlw=0.59*z/turb_state%sigw
    else
      turb_state%tlw=0.15*turb_state%h/turb_state%sigw*(1.-exp(-5*turb_state%zeta))
    endif


  !*********************
  ! 3. Stable conditions
  !*********************

  else
    turb_state%sigu=1.e-2+2.*turb_state%ust*(1.-turb_state%zeta)   ! Eq. 7.20 Hanna 1982
    turb_state%sigv=1.e-2+1.3*turb_state%ust*(1.-turb_state%zeta)  ! Eq. 7.19 Hanna 1982
    turb_state%sigw=turb_state%sigv
    turb_state%dsigwdz=-1.3*turb_state%ust/turb_state%h            ! ???
    turb_state%tlu=0.15*turb_state%h/turb_state%sigu*(sqrt(turb_state%zeta))  ! Eq. 7.22 Hanna 1982
    turb_state%tlv=0.467*turb_state%tlu                 ! Eq. 7.23 Hanna 1982
    turb_state%tlw=0.1*turb_state%h/turb_state%sigw*turb_state%zeta**0.8      ! Eq. 7.24 Hanna 1982
  endif


  turb_state%tlu=max(10.,turb_state%tlu)
  turb_state%tlv=max(10.,turb_state%tlv)
  turb_state%tlw=max(30.,turb_state%tlw)

  if (turb_state%dsigwdz.eq.0.) turb_state%dsigwdz=1.e-10
end subroutine hanna

subroutine hanna1(z)
  !                  i
  !*****************************************************************************
  !                                                                            *
  !   Computation of \sigma_i and \tau_L based on the scheme of Hanna (1982)   *
  !   Source: 'Atmospheric Turbulence and Air Polution', chapter 4 and 7,      *
  !   J.A. Businger, edited by F.T.M. Nieuwstadt and H. van Dop                * 
  !                                                                            *
  !   Author: A. Stohl                                                         *
  !                                                                            *
  !   4 December 1997                                                          *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! turb_state%dsigwdz [1/s]     vertical gradient of turb_state%sigw                                *
  ! turb_state%ol [m]            Obukhov length                                           *
  ! turb_state%sigu, turb_state%sigv, turb_state%sigw  standard deviations of turbulent velocity fluctuations   *
  ! turb_state%tlu [s]           Lagrangian time scale for the along wind component.      *
  ! turb_state%tlv [s]           Lagrangian time scale for the cross wind component.      *
  ! turb_state%tlw [s]           Lagrangian time scale for the vertical wind component.   *
  ! turb_state%ust, ustar [m/s]  friction velocity                                        *
  ! turb_state%wst, wstar [m/s]  convective velocity scale                                *
  !                                                                            *
  !*****************************************************************************

  implicit none

  real :: z,s1,s2



  !**********************
  ! 1. Neutral conditions
  !**********************

  if (turb_state%h/abs(turb_state%ol).lt.1.) then

    turb_state%ust=max(1.e-4,turb_state%ust)

    ! Eq. 7.25 Hanna 1982: turb_state%sigu/turb_state%ust=2.0*exp(-3*f*z/turb_state%ust),
    ! where f, the Coriolis parameter, is set to 1e-4
    turb_state%sigu=2.0*turb_state%ust*exp(-3.e-4*z/turb_state%ust)
    turb_state%sigu=max(turb_state%sigu,1.e-5)

    ! Eq. 7.26 Hanna 1982: turb_state%sigv/turb_state%ust=turb_state%sigw/turb_state%ust=1.3*exp(-2*f*z/turb_state%ust),
    ! where f, the Coriolis parameter, is set to 1e-4
    turb_state%sigv=1.3*turb_state%ust*exp(-2.e-4*z/turb_state%ust)
    turb_state%sigv=max(turb_state%sigv,1.e-5)
    turb_state%sigw=turb_state%sigv

    ! ???
    turb_state%dsigw2dz=-6.76e-4*turb_state%ust*exp(-4.e-4*z/turb_state%ust)

    ! Eq.7.27 Hanna 1982: TL=0.5*z/turb_state%sigw/(1+15*f*z/turb_state%ust) assumed to be valid
    ! for all three components
    turb_state%tlu=0.5*z/turb_state%sigw/(1.+1.5e-3*z/turb_state%ust)
    turb_state%tlv=turb_state%tlu
    turb_state%tlw=turb_state%tlu


  !***********************
  ! 2. Unstable conditions
  !***********************

  else if (turb_state%ol.lt.0.) then


  ! Determine sigmas
  !*****************

    ! Eq. 4.15 Caughey 1982
    turb_state%sigu=turb_state%ust*(12.-0.5*turb_state%h/turb_state%ol)**0.33333
    turb_state%sigu=max(turb_state%sigu,1.e-6)
    turb_state%sigv=turb_state%sigu

    ! Eq. 7.15 Hanna 1982
    if (turb_state%zeta.lt.0.03) then
      turb_state%sigw=0.96*turb_state%wst*(3*turb_state%zeta-turb_state%ol/turb_state%h)**0.33333
      turb_state%dsigw2dz=1.8432*turb_state%wst*turb_state%wst/ &
        turb_state%h*(3*turb_state%zeta- &
        turb_state%ol/turb_state%h)**(-0.33333)
    else if (turb_state%zeta.lt.0.4) then
      s1=0.96*(3*turb_state%zeta-turb_state%ol/turb_state%h)**0.33333
      s2=0.763*turb_state%zeta**0.175
      if (s1.lt.s2) then
        turb_state%sigw=turb_state%wst*s1
        turb_state%dsigw2dz=1.8432*turb_state%wst*turb_state%wst/ &
          turb_state%h*(3*turb_state%zeta- &
          turb_state%ol/turb_state%h)**(-0.33333)
      else
        turb_state%sigw=turb_state%wst*s2
        turb_state%dsigw2dz=0.203759*turb_state%wst*turb_state%wst/turb_state%h*turb_state%zeta**(-0.65)
      endif
    else if (turb_state%zeta.lt.0.96) then
      turb_state%sigw=0.722*turb_state%wst*(1-turb_state%zeta)**0.207
      turb_state%dsigw2dz=-.215812*turb_state%wst*turb_state%wst/turb_state%h*(1-turb_state%zeta)**(-0.586)
    else if (turb_state%zeta.lt.1.00) then
      turb_state%sigw=0.37*turb_state%wst
      turb_state%dsigw2dz=0.
    endif
    turb_state%sigw=max(turb_state%sigw,1.e-6)


  ! Determine average Lagrangian time scale
  !****************************************

    ! Eq. 7.17 Hanna  1982
    turb_state%tlu=0.15*turb_state%h/turb_state%sigu
    turb_state%tlv=turb_state%tlu
    if (z.lt.abs(turb_state%ol)) then
      turb_state%tlw=0.1*z/(turb_state%sigw*(0.55-0.38*abs(z/turb_state%ol)))
    else if (turb_state%zeta.lt.0.1) then
      turb_state%tlw=0.59*z/turb_state%sigw
    else
      turb_state%tlw=0.15*turb_state%h/turb_state%sigw*(1.-exp(-5*turb_state%zeta))
    endif


  !*********************
  ! 3. Stable conditions
  !*********************

  else
    turb_state%sigu=2.*turb_state%ust*(1.-turb_state%zeta)
    turb_state%sigv=1.3*turb_state%ust*(1.-turb_state%zeta)
    turb_state%sigu=max(turb_state%sigu,1.e-6)
    turb_state%sigv=max(turb_state%sigv,1.e-6)
    turb_state%sigw=turb_state%sigv
    turb_state%dsigw2dz=3.38*turb_state%ust*turb_state%ust*(turb_state%zeta-1.)/turb_state%h
    turb_state%tlu=0.15*turb_state%h/turb_state%sigu*(sqrt(turb_state%zeta))
    turb_state%tlv=0.467*turb_state%tlu
    turb_state%tlw=0.1*turb_state%h/turb_state%sigw*turb_state%zeta**0.8
  endif




  turb_state%tlu=max(10.,turb_state%tlu)
  turb_state%tlv=max(10.,turb_state%tlv)
  turb_state%tlw=max(30.,turb_state%tlw)
end subroutine hanna1

subroutine hanna_short(z)
  !                       i
  !*****************************************************************************
  !                                                                            *
  !   Computation of \sigma_i and \tau_L based on the scheme of Hanna (1982)   *
  !                                                                            *
  !   Author: A. Stohl                                                         *
  !                                                                            *
  !   4 December 1997                                                          *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! turb_state%dsigwdz [1/s]     vertical gradient of turb_state%sigw                                *
  ! turb_state%ol [m]            Obukhov length                                           *
  ! turb_state%sigu, turb_state%sigv, turb_state%sigw  standard deviations of turbulent velocity fluctuations   *
  ! turb_state%tlu [s]           Lagrangian time scale for the along wind component.      *
  ! turb_state%tlv [s]           Lagrangian time scale for the cross wind component.      *
  ! turb_state%tlw [s]           Lagrangian time scale for the vertical wind component.   *
  ! turb_state%ust, ustar [m/s]  friction velocity                                        *
  ! turb_state%wst, wstar [m/s]  convective velocity scale                                *
  !                                                                            *
  !*****************************************************************************

  implicit none

  real :: z



  !**********************
  ! 1. Neutral conditions
  !**********************

  if (turb_state%h/abs(turb_state%ol).lt.1.) then
    turb_state%ust=max(1.e-4,turb_state%ust)
    turb_state%sigw=1.3*exp(-2.e-4*z/turb_state%ust)
    turb_state%dsigwdz=-2.e-4*turb_state%sigw
    turb_state%sigw=turb_state%sigw*turb_state%ust+1.e-2
    turb_state%tlw=0.5*z/turb_state%sigw/(1.+1.5e-3*z/turb_state%ust)


  !***********************
  ! 2. Unstable conditions
  !***********************

  else if (turb_state%ol.lt.0.) then


  ! Determine sigmas
  !*****************

    turb_state%sigw=sqrt(1.2*turb_state%wst**2*(1.-.9*turb_state%zeta)*turb_state%zeta**0.66666+ &
         (1.8-1.4*turb_state%zeta)*turb_state%ust**2)+1.e-2
    turb_state%dsigwdz=0.5/turb_state%sigw/turb_state%h*(-1.4*turb_state%ust**2+turb_state%wst**2* &
         (0.8*max(turb_state%zeta,1.e-3)**(-.33333)-1.8*turb_state%zeta**0.66666))


  ! Determine average Lagrangian time scale
  !****************************************

    if (z.lt.abs(turb_state%ol)) then
      turb_state%tlw=0.1*z/(turb_state%sigw*(0.55-0.38*abs(z/turb_state%ol)))
    else if (turb_state%zeta.lt.0.1) then
      turb_state%tlw=0.59*z/turb_state%sigw
    else
      turb_state%tlw=0.15*turb_state%h/turb_state%sigw*(1.-exp(-5*turb_state%zeta))
    endif


  !*********************
  ! 3. Stable conditions
  !*********************

  else
    turb_state%sigw=1.e-2+1.3*turb_state%ust*(1.-turb_state%zeta)
    turb_state%dsigwdz=-1.3*turb_state%ust/turb_state%h
    turb_state%tlw=0.1*turb_state%h/turb_state%sigw*turb_state%zeta**0.8
  endif


  turb_state%tlu=max(10.,turb_state%tlu)
  turb_state%tlv=max(10.,turb_state%tlv)
  turb_state%tlw=max(30.,turb_state%tlw)
  if (turb_state%dsigwdz.eq.0.) turb_state%dsigwdz=1.e-10
end subroutine hanna_short

subroutine windalign(u,v,ffap,ffcp,ux,vy)
  !                     i i  i    i   o  o
  !*****************************************************************************
  !                                                                            *
  !  Transformation from along- and cross-wind components to u and v           *
  !  components.                                                               *
  !                                                                            *
  !     Author: A. Stohl                                                       *
  !                                                                            *
  !     3 June 1996                                                            *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! ffap  turbulent wind in along wind direction                               *
  ! ffcp  turbulent wind in cross wind direction                               *
  ! u     main wind component in x direction                                   *
  ! ux    turbulent wind in x direction                                        *
  ! v     main wind component in y direction                                   *
  ! vy    turbulent wind in y direction                                        *
  !                                                                            *
  !*****************************************************************************

  implicit none

  real :: u,v,ffap,ffcp,ux,vy,ffinv,ux1,ux2,vy1,vy2,sinphi,cosphi
  real,parameter :: eps=1.e-30


  ! Transform along wind components
  !********************************

  ffinv=1./max(sqrt(u*u+v*v),eps)
  sinphi=v*ffinv
  vy1=sinphi*ffap
  cosphi=u*ffinv
  ux1=cosphi*ffap


  ! Transform cross wind components
  !********************************

  ux2=-sinphi*ffcp
  vy2=cosphi*ffcp


  ! Add contributions from along and cross wind components
  !*******************************************************

  ux=ux1+ux2
  vy=vy1+vy2
end subroutine windalign

end module turbulence_mod
