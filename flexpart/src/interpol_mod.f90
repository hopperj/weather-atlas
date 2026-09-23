  !*****************************************************************************
  !                                                                            *
  ! L. Bakels 2022: This module contains all interpolation subroutines         *
  !                 Code has been organised into subroutines                   *
  !                 Vertical logarithmic interpolation is optional (par_mod)   *
  !                                                                            *
  !*****************************************************************************

module interpol_mod
  use par_mod
  use com_mod
  use windfields_mod
  use particle_mod

  implicit none

  real,allocatable,dimension(:,:) ::          &
    uprof,vprof,wprof,              &
    usigprof,vsigprof,wsigprof,     &
    rhoprof,rhogradprof
  logical,allocatable,dimension(:,:) ::       &
    indzindicator,depoindicator

  type :: interpolation_thread_state
    real :: u,v,w,usig,vsig,wsig
    real :: p1,p2,p3,p4,ddx,ddy,rddx,rddy,dtt,dt1,dt2
    real :: xtn,ytn
    real :: dz1out,dz2out
    integer :: nix,njy
    integer :: ix,jy,ixp,jyp,ngrid,indz,indzp
    integer :: induv,indpuv
    logical :: lbounds(2) ! marking particles below or above bounds
#ifdef ETA
    real :: ueta,veta,weta,wsigeta
    integer :: indzeta,indzpeta
    logical :: lbounds_w(2),lbounds_uv(2)
#endif
  end type interpolation_thread_state

  ! Bundle hot interpolation scalars into one TLS object. This preserves the
  ! original per-thread state but lets GCC hoist a single emulated TLS lookup.
  type(interpolation_thread_state) :: interp_state
!$OMP THREADPRIVATE(interp_state)

#ifdef ETA
  real,allocatable,dimension(:,:) :: wprofeta ! ,wsigprofeta
#endif

#ifdef ETA
  private :: interpol_wind_eta,stdev_eta,interpol_partoutput_val_eta
#else
  private :: interpol_wind_meter,stdev_meter,interpol_partoutput_val_meter
#endif

  interface hor_interpol
    procedure hor_interpol_4d,hor_interpol_2d
  end interface hor_interpol
  
  interface hor_interpol_nest
    procedure hor_interpol_4d_nest,hor_interpol_2d_nest
  end interface hor_interpol_nest

  interface find_ngrid
    procedure find_ngrid_dp, find_ngrid_sp
  end interface find_ngrid

contains

subroutine alloc_interpol ! wsigprofeta(nzmax,numthreads),
  implicit none 
  integer :: stat

  allocate( uprof(nzmax,numthreads),vprof(nzmax,numthreads),wprof(nzmax,numthreads),      &
    usigprof(nzmax,numthreads),vsigprof(nzmax,numthreads),wsigprof(nzmax,numthreads),  &
    rhoprof(nzmax,numthreads),rhogradprof(nzmax,numthreads), &
    indzindicator(nzmax,numthreads),stat=stat)
  if (stat.ne.0) error stop "Could not allocate interpol prof arrays"
#ifdef ETA
  allocate( wprofeta(nzmax,numthreads),stat=stat)
  if (stat.ne.0) error stop "Could not allocate wprofeta"
#endif
  if (DRYDEP) then
    allocate( depoindicator(maxspec,numthreads),stat=stat)
    if (stat.ne.0) error stop "Could not allocate depoindicator"
  endif
end subroutine alloc_interpol

subroutine dealloc_interpol ! wsigprofeta,
  deallocate(uprof,vprof,wprof,      &
    usigprof,vsigprof,wsigprof,  &
    rhoprof,rhogradprof,indzindicator)
#ifdef ETA
  deallocate(wprofeta)
#endif
  if (DRYDEP) deallocate( depoindicator )
end subroutine dealloc_interpol

subroutine init_interpol(itime,xt,yt,zt,zteta)

  ! This routine initialises all important values used in the interpol module
  ! This includes:
  ! - The current grid number in which the particle is positioned
  ! - The interpolation fractions of the grid (x,y,z) and of time

  integer, intent(in) :: itime             ! time step
  real, intent(in)    :: xt,yt             ! particle positions
  real, intent(in)    :: zt                ! height in meters
  real, intent(in)    :: zteta             ! height in eta coordinates

  call find_ngrid(xt,yt)
  call find_grid_indices(xt,yt)
  call find_grid_distances(xt,yt)
  call find_time_vars(itime)
  call find_z_level(zt,zteta)

end subroutine init_interpol

subroutine find_grid_indices(xt,yt)

  real, intent(in) :: xt,yt                 ! particle positions

  if (interp_state%ngrid.gt.0) then ! Nest
    interp_state%xtn=(xt-xln(interp_state%ngrid))*xresoln(interp_state%ngrid)
    interp_state%ytn=(yt-yln(interp_state%ngrid))*yresoln(interp_state%ngrid)
    ! interp_state%ix=int(interp_state%xtn)
    ! interp_state%jy=int(interp_state%ytn)
    ! interp_state%nix=nint(interp_state%xtn)
    ! interp_state%njy=nint(interp_state%ytn)
    interp_state%nix=max(min(int(interp_state%xtn),nxn(interp_state%ngrid)-1),0)
    interp_state%njy=max(min(int(interp_state%ytn),nyn(interp_state%ngrid)-1),0)
    interp_state%ix=interp_state%nix
    interp_state%jy=interp_state%njy
    interp_state%ixp=interp_state%ix+1
    interp_state%jyp=interp_state%jy+1
    return
  else
    interp_state%ix=int(xt)
    interp_state%jy=int(yt)
    interp_state%nix=interp_state%ix!nint(xt)
    interp_state%njy=interp_state%jy!nint(yt)
    interp_state%ixp=interp_state%ix+1
    interp_state%jyp=interp_state%jy+1
  endif

  ! eso: Temporary fix for particle exactly at north pole
  if (interp_state%jyp.ge.nymax) then
    write(*,*) 'WARNING: interpol_mod.f90 interp_state%jyp >= nymax. xt,yt:',xt,yt
    interp_state%jyp=interp_state%jyp-1
  end if

  if (interp_state%ixp.ge.nxmax) then
    write(*,*) 'WARNING: interpol_mod.f90 interp_state%ixp >= nxmax. xt,yt:',xt,yt
    interp_state%ixp=interp_state%ixp-nxmax
  end if

end subroutine find_grid_indices

subroutine find_grid_distances(xt,yt)

  implicit none 

  real, intent(in) :: xt,yt                 ! particle positions

  if (interp_state%ngrid.le.0) then
    interp_state%ddx=xt-real(interp_state%ix)
    interp_state%ddy=yt-real(interp_state%jy)
  else ! Nest
    interp_state%ddx=interp_state%xtn-real(interp_state%ix)
    interp_state%ddy=interp_state%ytn-real(interp_state%jy)
  endif
  interp_state%rddx=1.-interp_state%ddx
  interp_state%rddy=1.-interp_state%ddy
  interp_state%p1=interp_state%rddx*interp_state%rddy
  interp_state%p2=interp_state%ddx*interp_state%rddy
  interp_state%p3=interp_state%rddx*interp_state%ddy
  interp_state%p4=interp_state%ddx*interp_state%ddy

end subroutine find_grid_distances

subroutine find_time_vars(itime)

  integer, intent(in) :: itime             ! time step
  
  interp_state%dt1=real(itime-memtime(1))
  interp_state%dt2=real(memtime(2)-itime)
  interp_state%dtt=1./(interp_state%dt1+interp_state%dt2)  

end subroutine find_time_vars

subroutine find_z_level(zt,zteta)

  real, intent(in)     :: &
    zt,                   & ! height in meters
    zteta                   ! height in eta

#ifdef ETA
    call find_z_level_meters(zt)
    call find_z_level_eta(zteta)
#else
    call find_z_level_meters(zt)
#endif

end subroutine find_z_level

subroutine find_z_level_meters(zt)

  real, intent(in)     :: zt       ! height in meters
  integer              :: i

  interp_state%indz=nz-1
  interp_state%indzp=nz
  if (zt.le.height(1)) then
    interp_state%lbounds(1)=.true.
    interp_state%lbounds(2)=.false.
    interp_state%indz=1
    interp_state%indzp=2
  else if (zt.ge.height(nz)) then
    interp_state%lbounds(1)=.false.
    interp_state%lbounds(2)=.true.
  else
    interp_state%lbounds(1)=.false.
    interp_state%lbounds(2)=.false.
    do i=2,nz
      if (height(i).gt.zt) then
        interp_state%indz=i-1
        interp_state%indzp=i
        exit
      endif
    end do
  endif

end subroutine find_z_level_meters

#ifdef ETA
subroutine find_z_level_eta(zteta)

  real, intent(in)       :: zteta    ! height in eta coordinates

  call find_z_level_eta_w(zteta)

  call find_z_level_eta_uv(zteta)

end subroutine find_z_level_eta

subroutine find_z_level_eta_w(zteta)

  real, intent(in)       :: zteta    ! height in eta coordinates
  integer                :: i        ! loop variable

  interp_state%indzeta=nz-1
  interp_state%indzpeta=nz
  ! Flag particles that are above or below bounds
  if (zteta.ge.wheight(1)) then
    interp_state%lbounds_w(1)=.true.
    interp_state%lbounds_w(2)=.false.
    interp_state%indzeta=1
    interp_state%indzpeta=2
  else if (zteta.le.wheight(nz)) then
    interp_state%lbounds_w(1)=.false.
    interp_state%lbounds_w(2)=.true.
  else
    interp_state%lbounds_w(1)=.false.
    interp_state%lbounds_w(2)=.false.
    do i=2,nz
      if (wheight(i).lt.zteta) then
        interp_state%indzeta=i-1
        interp_state%indzpeta=i
        exit
      endif
    end do
  endif

end subroutine find_z_level_eta_w

subroutine find_z_level_eta_uv(zteta)

  real, intent(in)       :: zteta    ! height in eta coordinates
  integer                :: i        ! loop variable

  interp_state%induv=nz-1
  interp_state%indpuv=nz
  if (zteta.gt.uvheight(1)) then
    interp_state%lbounds_uv(1)=.true.
    interp_state%lbounds_uv(2)=.false.
    interp_state%induv=1 
    interp_state%indpuv=2
  else if (zteta.lt.uvheight(nz)) then
    interp_state%lbounds_uv(1)=.false.
    interp_state%lbounds_uv(2)=.true.
  else
    interp_state%lbounds_uv(1)=.false.
    interp_state%lbounds_uv(2)=.false.
    do i=2,nz
      if (uvheight(i).lt.zteta) then
        interp_state%induv=i-1
        interp_state%indpuv=i
        exit
      endif
    end do
  endif

end subroutine find_z_level_eta_uv
#endif

subroutine find_vert_vars(vertlevels,zpos,zlevel,dz1,dz2,bounds,wlevel)

  !*****************************************************************************
  !                                                                            *
  ! This subroutine computes the vertical interpolation variables              *
  ! logarithmically, unless log_interpol=.false. in the par_mod                *
  !                                                                            *
  ! Author: L. Bakels                                                          *
  !*****************************************************************************

  real, intent(in)    :: vertlevels(:)    ! vertical levels in coordinate system
  real, intent(in)    :: zpos             ! verticle particle position
  integer, intent(in) :: zlevel           ! vertical level of interest
  logical, intent(in) :: bounds(2),wlevel ! flag marking if particles are
                                          ! outside bounds  
  real, intent(inout) :: dz1,dz2          ! fractional distance to point 1 
                                          ! (closer to ground) and 2
  real                :: dz,dh1,dh,pfact
  real                :: psint1(2),psint,pr1,pr2,pr_test 
                                          ! pressure of encompassing levels
  integer             :: m

  ! Only do logarithmic interpolation when using ETA coordinates, since the
  ! levels are following pressure, while METER levels are linear.
  !##############################################################
  if (.not. log_interpol) then
    call find_vert_vars_lin(vertlevels,zpos,zlevel,dz1,dz2,bounds)
    return
  endif
  
  ! To check if taking the logarithm is safe
  if (wlevel) then
    pr_test=akm(zlevel+1)+bkm(zlevel+1)
  else
    pr_test=akz(zlevel+1)+bkz(zlevel+1)
  endif

  ! If the particle is below bounds (bounds(1)==.true.):
  if (bounds(1)) then
    dz1=0.
    dz2=1.
  ! If above bounds (bounds(2)==.true.):
  else if (bounds(2)) then
    dz1=1.
    dz2=0.

  ! Instead of the linear z variables, we need the ones that correspond to 
  ! the pressure of the height of the particle in relation to the model levels
  !***************************************************************************
  else if (pr_test.eq.0) then
    dz=1./(vertlevels(zlevel+1)-vertlevels(zlevel))
    dz1=(zpos-vertlevels(zlevel))*dz
    dz2=(vertlevels(zlevel+1)-zpos)*dz
  else
    if (interp_state%ngrid.le.0) then
      do m=1,2
        call hor_interpol(ps,psint1(m),1,memind(m),1)
      end do
    else
      do m=1,2
        call hor_interpol_nest(psn,psint1(m),1,memind(m),1)
      end do
    endif
    call temporal_interpolation(psint1(1),psint1(2),psint)
    dh = vertlevels(zlevel+1)-vertlevels(zlevel)
    dh1 = zpos - vertlevels(zlevel)
    if (wlevel) then
      pr1=akm(zlevel) + bkm(zlevel)*psint
      pr2=akm(zlevel+1) + bkm(zlevel+1)*psint
    else
      pr1=akz(zlevel) + bkz(zlevel)*psint
      pr2=akz(zlevel+1) + bkz(zlevel+1)*psint
    endif
    pfact = log(pr2/pr1)*dh1/dh  
    dz = 1./(pr2-pr1)
    dz1 = pr1*(exp(pfact)-1.)*dz 
    dz2 = 1.-dz1
  endif
  ! else if ((vertlevels(zlevel).eq.0).or.(vertlevels(zlevel+1).eq.0)) then
  !   ! Linear interpolation for bottom or top layer is zero
  !   dz=1./(vertlevels(zlevel+1)-vertlevels(zlevel))
  !   dz1=(zpos-vertlevels(zlevel))*dz
  !   dz2=(vertlevels(zlevel+1)-zpos)*dz
  ! else 
  !   ! Logaritmic interpolation
  !   dz=1./(log(vertlevels(zlevel+1))-log(vertlevels(zlevel)))
  !   dz1=(log(zpos)-log(vertlevels(zlevel)))*dz
  !   dz2=(log(vertlevels(zlevel+1))-log(zpos))*dz
  ! endif
end subroutine find_vert_vars

subroutine find_vert_vars_lin(vertlevels,zpos,zlevel,dz1,dz2,bounds)

  real, intent(in)    :: vertlevels(:)   ! vertical levels in coordinate system
  real, intent(in)    :: zpos            ! verticle particle position
  integer, intent(in) :: zlevel          ! vertical level of interest
  logical, intent(in) :: bounds(2)       ! flag marking if particles are outside
                                         ! bounds  
  real, intent(inout) :: dz1,dz2         ! fractional distance to point 1
                                         ! (closer to ground) and 2
  real                :: dz

  ! If the particle is below bounds (bounds(1)==.true.):
  if (bounds(1)) then
    dz1=0.
    dz2=1.
  ! If above bounds (bounds(2)==.true.):
  else if (bounds(2)) then
    dz1=1.
    dz2=0.
  else
    dz=1./(vertlevels(zlevel+1)-vertlevels(zlevel))
    dz1=(zpos-vertlevels(zlevel))*dz
    dz2=(vertlevels(zlevel+1)-zpos)*dz
  endif
end subroutine find_vert_vars_lin

subroutine find_ngrid_dp(xt,yt)

  real eps           
  real(kind=dp), intent(in) :: xt,yt ! particle positions on grid
  integer :: j

  eps=nxmax/3.e5
  if (nglobal.and.(real(yt).gt.switchnorthg)) then
    interp_state%ngrid=-1
  else if (sglobal.and.(real(yt).lt.switchsouthg)) then
    interp_state%ngrid=-2
  else
    interp_state%ngrid=0
    ! Temporary fix for nested layer edges: replaced eps with dxn and dyn (LB)
    do j=numbnests,1,-1
      if (real(xt).gt.xln(j)+dxn(j) .and. real(xt).lt.xrn(j)-dxn(j) .and. &
          real(yt).gt.yln(j)+dyn(j) .and. real(yt).lt.yrn(j)-dyn(j)) then
        interp_state%ngrid=j
        exit
      endif
    end do
  endif
  
end subroutine find_ngrid_dp

subroutine find_ngrid_sp(xt,yt)

  real :: eps           
  real, intent(in) :: xt,yt ! particle positions on grid
  integer :: j

  eps=nxmax/3.e5
  if (nglobal .and. yt.gt.switchnorthg) then
    interp_state%ngrid=-1
  else if (sglobal .and. yt.lt.switchsouthg) then
    interp_state%ngrid=-2
  else
    interp_state%ngrid=0
    ! Temporary fix for nested layer edges: replaced eps with dxn and dyn (LB)
    do j=numbnests,1,-1
      if (xt.gt.xln(j)+dxn(j) .and. xt.lt.xrn(j)-dxn(j) .and. &
          yt.gt.yln(j)+dyn(j) .and. yt.lt.yrn(j)-dyn(j)) then
        interp_state%ngrid=j
        exit
      endif
    end do
  endif
end subroutine find_ngrid_sp

subroutine hor_interpol_4d(field,output,zlevel,indexh,ztot)

  integer, intent(in) :: zlevel,ztot,indexh   ! interpolation z level, z
  real, intent(in)    :: field(0:nxmax-1,0:nymax-1,ztot,numwfmem) 
   ! input field to interpolate
  real, intent(inout) :: output  ! interpolated values

  output=interp_state%p1*field(interp_state%ix ,interp_state%jy ,zlevel,indexh) &
       + interp_state%p2*field(interp_state%ixp,interp_state%jy ,zlevel,indexh) &
       + interp_state%p3*field(interp_state%ix ,interp_state%jyp,zlevel,indexh) &
       + interp_state%p4*field(interp_state%ixp,interp_state%jyp,zlevel,indexh)
end subroutine hor_interpol_4d

subroutine hor_interpol_2d(field,output)
  implicit none 

  real, intent(in)    :: field(0:nxmax-1,0:nymax-1)       ! 2D imput field
  real, intent(inout) :: output                           ! Interpolated value

  output=interp_state%p1*field(interp_state%ix ,interp_state%jy) &
         + interp_state%p2*field(interp_state%ixp,interp_state%jy) &
         + interp_state%p3*field(interp_state%ix ,interp_state%jyp) &
         + interp_state%p4*field(interp_state%ixp,interp_state%jyp)
end subroutine hor_interpol_2d

subroutine hor_interpol_4d_nest(field,output,zlevel,indexh,ztot)

  integer, intent(in) :: zlevel,ztot,indexh   ! interpolation z level, z
  real, intent(in)    :: field(0:nxmaxn-1,0:nymaxn-1,ztot,numwfmem,numbnests) 
                                              ! input field to interpolate 
  real, intent(inout) :: output               ! interpolated values

  output=interp_state%p1*field(interp_state%ix ,interp_state%jy ,zlevel,indexh,interp_state%ngrid) &
       + interp_state%p2*field(interp_state%ixp,interp_state%jy ,zlevel,indexh,interp_state%ngrid) &
       + interp_state%p3*field(interp_state%ix ,interp_state%jyp,zlevel,indexh,interp_state%ngrid) &
       + interp_state%p4*field(interp_state%ixp,interp_state%jyp,zlevel,indexh,interp_state%ngrid)
end subroutine hor_interpol_4d_nest

subroutine hor_interpol_2d_nest(field,output)

  real, intent(in)    :: field(0:nxmaxn-1,0:nymaxn-1,numbnests) 
                                          ! input field to interpolate
  real, intent(inout) :: output           ! interpolated values

  output=interp_state%p1*field(interp_state%ix ,interp_state%jy ,interp_state%ngrid) &
       + interp_state%p2*field(interp_state%ixp,interp_state%jy ,interp_state%ngrid) &
       + interp_state%p3*field(interp_state%ix ,interp_state%jyp,interp_state%ngrid) &
       + interp_state%p4*field(interp_state%ixp,interp_state%jyp,interp_state%ngrid)
end subroutine hor_interpol_2d_nest

subroutine temporal_interpolation(time1,time2,output)

  real, intent(in)    :: time1,time2     ! input data at two timesteps 
  real, intent(inout) :: output          ! interpolated data

  output=(time1*interp_state%dt2+time2*interp_state%dt1)*interp_state%dtt
end subroutine temporal_interpolation

subroutine vert_interpol(input1,input2,dz1,dz2,output)

  real, intent(in)    :: input1,input2   ! input data at two vertical levels, 
                                         ! 1 being closer to ground
  real, intent(in)    :: dz1,dz2         ! logarithmic interpolation values
  real, intent(inout) :: output          ! interpolated data

  output = input1*dz2 + input2*dz1 ! input1**dz2 * input2**dz1
end subroutine vert_interpol

subroutine bilin_spatial_interpol(field,output,zlevel,dz1,dz2,ztot)

  integer, intent(in) :: zlevel,ztot        ! interpolation z level
  real, intent(in)    :: field(0:nxmax-1,0:nymax-1,ztot,numwfmem)  
                                            ! input field to interpolate
  real, intent(in)    :: dz1,dz2
  real, intent(inout) :: output(2)          ! interpolated values
  integer             :: m,n,indzh
  real                :: output1(2)

  do m=1,2
    
    do n=1,2
      indzh=zlevel+n-1
      call hor_interpol_4d(field,output1(n),indzh,memind(m),ztot)
    end do
    
    !**********************************
    ! 2.) Linear vertical interpolation on logarithmic scale
    !**********************************    
    call vert_interpol(output1(1),output1(2),dz1,dz2,output(m))
    
  end do
  
end subroutine bilin_spatial_interpol

subroutine bilin_spatial_interpol_nest(field,output,zlevel,dz1,dz2,ztot)

  integer, intent(in) :: zlevel,ztot       ! interpolation z level
  real, intent(in)    :: field(0:nxmaxn-1,0:nymaxn-1,ztot,numwfmem,numbnests)  
                                           ! input field to interpolate
  real, intent(in)    :: dz1,dz2
  real, intent(inout) :: output(2)         ! interpolated values
  integer             :: m,n,indzh
  real                :: output1(2)

  do m=1,2
  
    do n=1,2
      indzh=zlevel+n-1
      call hor_interpol_4d_nest(field,output1(n),indzh,memind(m),ztot)
    end do
    
    !**********************************
    ! 2.) Linear vertical interpolation on logarithmic scale
    !**********************************    
    call vert_interpol(output1(1),output1(2),dz1,dz2,output(m))
    
  end do
  
end subroutine bilin_spatial_interpol_nest

subroutine compute_sl_sq(field,sl,sq,zlevel,indexh,ztot)

  integer, intent(in) :: zlevel,ztot,indexh   ! interpolation z levels
  real, intent(in)    :: field(0:nxmax-1,0:nymax-1,ztot,numwfmem) 
                                              ! input field to interpolate
  real, intent(inout) :: sl,sq                ! standard deviation

  sl=sl+field(interp_state%ix ,interp_state%jy ,zlevel,indexh)+field(interp_state%ixp,interp_state%jy ,zlevel,indexh) &
       +field(interp_state%ix ,interp_state%jyp,zlevel,indexh)+field(interp_state%ixp,interp_state%jyp,zlevel,indexh)

  sq=sq+field(interp_state%ix ,interp_state%jy ,zlevel,indexh)*field(interp_state%ix ,interp_state%jy ,zlevel,indexh)+ &
        field(interp_state%ixp,interp_state%jy ,zlevel,indexh)*field(interp_state%ixp,interp_state%jy ,zlevel,indexh)+ &
        field(interp_state%ix ,interp_state%jyp,zlevel,indexh)*field(interp_state%ix ,interp_state%jyp,zlevel,indexh)+ &
        field(interp_state%ixp,interp_state%jyp,zlevel,indexh)*field(interp_state%ixp,interp_state%jyp,zlevel,indexh)

end subroutine compute_sl_sq

subroutine compute_sl_sq_nest(field,sl,sq,zlevel,indexh,ztot)
  integer, intent(in) :: zlevel,ztot,indexh   ! interpolation z levels
  real, intent(in)    :: field(0:nxmaxn-1,0:nymaxn-1,ztot,numwfmem,numbnests) 
                                              ! input field to interpolate
  real, intent(inout) :: sl,sq                ! standard deviation

  sl=sl+field(interp_state%ix,interp_state%jy,zlevel,indexh, &
    interp_state%ngrid)+field(interp_state%ixp,interp_state%jy,zlevel, &
    indexh,interp_state%ngrid)+field(interp_state%ix,interp_state%jyp, &
    zlevel,indexh,interp_state%ngrid)+field(interp_state%ixp, &
    interp_state%jyp,zlevel,indexh,interp_state%ngrid)

  sq=sq+field(interp_state%ix,interp_state%jy,zlevel,indexh, &
    interp_state%ngrid)*field(interp_state%ix,interp_state%jy,zlevel, &
    indexh,interp_state%ngrid)+field(interp_state%ixp,interp_state%jy, &
    zlevel,indexh,interp_state%ngrid)*field(interp_state%ixp, &
    interp_state%jy,zlevel,indexh,interp_state%ngrid)+field( &
    interp_state%ix,interp_state%jyp,zlevel,indexh,interp_state%ngrid)* &
    field(interp_state%ix,interp_state%jyp,zlevel,indexh, &
    interp_state%ngrid)+field(interp_state%ixp,interp_state%jyp,zlevel, &
    indexh,interp_state%ngrid)*field(interp_state%ixp,interp_state%jyp, &
    zlevel,indexh,interp_state%ngrid)
end subroutine compute_sl_sq_nest

subroutine stdev(sl,sq,divisor,output)

  real, intent(in) :: sl,sq,divisor
  real, intent(out) :: output
  real :: xaux
  real,parameter      :: eps=1.0e-30

  xaux= sq - sl*sl/divisor

  if (xaux.lt.eps) then
    output=0.
  else
    output=sqrt(xaux/(divisor-1.))
  endif

end subroutine stdev

! Interpolation functions
!************************

subroutine interpol_pbl(itime,xt,yt,zt,zteta,ithread)
  !                          i   i  i  i
  !*****************************************************************************
  !                                                                            *
  !  This subroutine interpolates everything that is needed for calculating the*
  !  dispersion.                                                               *
  !                                                                            *
  !    Author: A. Stohl                                                        *
  !                                                                            *
  !    16 December 1997                                                        *
  !                                                                            *
  !  Revision March 2005 by AST : all output variables in common block cal-    *
  !                               culation of standard deviation done in this  *
  !                               routine rather than subroutine call in order *
  !                               to save computation time                     *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! itime [s]          current temporal position                               *
  ! memtime(3) [s]     times of the wind fields in memory                      *
  ! xt,yt,zt           coordinates position for which wind data shall be       *
  !                    culated                                                 *
  !                                                                            *
  ! Constants:                                                                 *
  !                                                                            *
  !*****************************************************************************

  use turbulence_mod

  integer,intent(in)  :: ithread ! If OMP, number of the thread, otherwise 1
  integer, intent(in) :: itime
  real, intent(in)    :: xt,yt,zt,zteta
  integer             :: m,n,indexh
  integer             :: iw(2),iweta(2)
  real                :: uh1(2),vh1(2),wh1(2),wetah1(2),rho1(2),rhograd1(2)
  real                :: dz1weta,dz2weta
  real,parameter      :: eps=1.0e-30

  ! Auxiliary variables needed for interpolation
  real :: ust1(2),wst1(2),oli1(2),oliaux

  !********************************************
  ! Multilinear interpolation in time and space
  !********************************************

  ! interp_state%ngrid and grid coordinates have already been definded, and are included
  ! in the input (for nested: interp_state%xtn,interp_state%ytn; for not nested: xts,yts)

  !************************************************************************
  ! Determine the lower left corner and its distance to the current position
  !*************************************************************************

  call find_grid_distances(xt,yt)

  ! Calculate variables for time interpolation
  !*******************************************

  call find_time_vars(itime)

  !********************************************************
  ! 1. Interpolate interp_state%u*, interp_state%w* and Obukhov length for turbulence
  !********************************************************

  ! a) Bilinear horizontal interpolation
  if (interp_state%ngrid.le.0) then ! No nest
    do m=1,2
      indexh=memind(m)
      call hor_interpol(ustar,ust1(m),1,memind(m),1)
      call hor_interpol(wstar,wst1(m),1,memind(m),1)
      call hor_interpol(oli,oli1(m),1,memind(m),1)
    end do
  else ! Nest
    do m=1,2
      indexh=memind(m)
      call hor_interpol_nest(ustarn,ust1(m),1,memind(m),1)
      call hor_interpol_nest(wstarn,wst1(m),1,memind(m),1)
      call hor_interpol_nest(olin,oli1(m),1,memind(m),1)
    end do
  endif    

  ! b) Temporal interpolation
  call temporal_interpolation(ust1(1),ust1(2),turb_state%ust)
  call temporal_interpolation(wst1(1),wst1(2),turb_state%wst)
  call temporal_interpolation(oli1(1),oli1(2),oliaux)

  if (oliaux.ne.0.) then
    turb_state%ol=1./oliaux
  else
    turb_state%ol=99999.
  endif

  ! Within the PBL, only METER coordinates are used
  ! with the exception of mesoscale turbulence,
  ! which uses interp_state%wsigeta computed in interpol_mesoscale
  !**************************************************

  ! Determine the level below the current position
  !***********************************************
  call find_z_level_meters(zt)

  iw(:)=(/ interp_state%indz, interp_state%indzp /)

  ! interp_state%w(eta) velocities are necessary for the Petterssen correction
  !**************************************************************
#ifdef ETA
    call find_z_level_eta(zteta)
    iweta(:)=(/ interp_state%indzeta, interp_state%indzpeta /)
#endif

  !**************************************
  ! 1.) Bilinear horizontal interpolation
  ! 2.) Temporal interpolation (linear)
  !**************************************
  
  ! Loop over 2 time steps and interp_state%indz levels
  !***************************************
  if (interp_state%ngrid.le.0) then ! No nest
    do n=1,2
      do m=1,2
        call hor_interpol(ww,wh1(m),iw(n),memind(m),nzmax)
#ifdef ETA
        call hor_interpol(wweta,wetah1(m),iweta(n),memind(m),nzmax)
#endif
        call hor_interpol(rho,rho1(m),iw(n),memind(m),nzmax)
        call hor_interpol(drhodz,rhograd1(m),iw(n),memind(m),nzmax)
        if (interp_state%ngrid.lt.0) then
          call hor_interpol(uupol,uh1(m),iw(n),memind(m),nzmax)
          call hor_interpol(vvpol,vh1(m),iw(n),memind(m),nzmax)
        else
          call hor_interpol(uu,uh1(m),iw(n),memind(m),nzmax)
          call hor_interpol(vv,vh1(m),iw(n),memind(m),nzmax)
        endif
      end do
      call temporal_interpolation(wh1(1),wh1(2),wprof(iw(n),ithread))
#ifdef ETA
      call temporal_interpolation(wetah1(1),wetah1(2),wprofeta(iweta(n),ithread))
#endif      
      call temporal_interpolation(uh1(1),uh1(2),uprof(iw(n),ithread))
      call temporal_interpolation(vh1(1),vh1(2),vprof(iw(n),ithread))
      call temporal_interpolation(rho1(1),rho1(2),rhoprof(iw(n),ithread))
      call temporal_interpolation(rhograd1(1),rhograd1(2),rhogradprof(iw(n),ithread))
    end do
  else ! Nest
    do n=1,2
      do m=1,2
        call hor_interpol_nest(wwn,wh1(m),iw(n),memind(m),nzmax)
#ifdef ETA
        call hor_interpol_nest(wwetan,wetah1(m),iweta(n),memind(m),nzmax)
#endif
        call hor_interpol_nest(uun,uh1(m),iw(n),memind(m),nzmax)
        call hor_interpol_nest(vvn,vh1(m),iw(n),memind(m),nzmax)
        call hor_interpol_nest(rhon,rho1(m),iw(n),memind(m),nzmax)
        call hor_interpol_nest(drhodzn,rhograd1(m),iw(n),memind(m),nzmax)
      end do
      call temporal_interpolation(wh1(1),wh1(2),wprof(iw(n),ithread))
#ifdef ETA
      call temporal_interpolation(wetah1(1),wetah1(2),wprofeta(iweta(n),ithread))
#endif
      call temporal_interpolation(uh1(1),uh1(2),uprof(iw(n),ithread))
      call temporal_interpolation(vh1(1),vh1(2),vprof(iw(n),ithread))
      call temporal_interpolation(rho1(1),rho1(2),rhoprof(iw(n),ithread))
      call temporal_interpolation(rhograd1(1),rhograd1(2),rhogradprof(iw(n),ithread))

      indzindicator(iw(n),ithread)=.false.
    end do
  endif

  ! Only necessary for the Petterssen correction
#ifdef ETA
  call find_vert_vars(wheight,zteta,interp_state%indzeta, &
    dz1weta,dz2weta,interp_state%lbounds_w,.true.)
  call vert_interpol(wprofeta(interp_state%indzeta,ithread),wprofeta(interp_state%indzpeta,ithread), &
    dz1weta,dz2weta,interp_state%weta)
#endif

end subroutine interpol_pbl

subroutine interpol_pbl_misslev(ithread)
  !*****************************************************************************
  !                                                                            *
  !  This subroutine interpolates interp_state%u,interp_state%v,interp_state%w, density and density gradients.        *
  !                                                                            *
  !    Author: A. Stohl                                                        *
  !                                                                            *
  !    16 December 1997                                                        *
  !    Update: 2 March 1999                                                    *
  !                                                                            *
  !  Revision March 2005 by AST : all output variables in common block cal-    *
  !                               culation of standard deviation done in this  *
  !                               routine rather than subroutine call in order *
  !                               to save computation time                     *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! n                  level                                                   *
  !                                                                            *
  ! Constants:                                                                 *
  !                                                                            *
  !*****************************************************************************

  integer,intent(in)  :: ithread ! number of OMP thread starting at 1
  real                :: uh1(2),vh1(2),wh1(2),rho1(2),rhograd1(2)
  integer             :: m,n,iw(2)

  ! Within the PBL, only METER coordinates are used
  ! with the exception of mesoscale turbulence,
  ! which uses interp_state%wsigeta computed in interpol_mesoscale
  !**************************************************

  !********************************************
  ! Multilinear interpolation in time and space
  !********************************************

  iw(:)=(/ interp_state%indz, interp_state%indzp /)
  do n=1,2
    if (indzindicator(iw(n),ithread)) then
      if (interp_state%ngrid.le.0) then ! No nest
        do m=1,2
          call hor_interpol(ww,wh1(m),iw(n),memind(m),nzmax)
          call hor_interpol(rho,rho1(m),iw(n),memind(m),nzmax)
          call hor_interpol(drhodz,rhograd1(m),iw(n),memind(m),nzmax)
          if (interp_state%ngrid.lt.0) then
            call hor_interpol(uupol,uh1(m),iw(n),memind(m),nzmax)
            call hor_interpol(vvpol,vh1(m),iw(n),memind(m),nzmax)
          else
            call hor_interpol(uu,uh1(m),iw(n),memind(m),nzmax)
            call hor_interpol(vv,vh1(m),iw(n),memind(m),nzmax)
          endif
        end do
      else ! Nest
        do m=1,2
          call hor_interpol_nest(wwn,wh1(m),iw(n),memind(m),nzmax)
          call hor_interpol_nest(uun,uh1(m),iw(n),memind(m),nzmax)
          call hor_interpol_nest(vvn,vh1(m),iw(n),memind(m),nzmax)
          call hor_interpol_nest(rhon,rho1(m),iw(n),memind(m),nzmax)
          call hor_interpol_nest(drhodzn,rhograd1(m),iw(n),memind(m),nzmax)
        end do
      endif
      call temporal_interpolation(wh1(1),wh1(2),wprof(iw(n),ithread))
      call temporal_interpolation(uh1(1),uh1(2),uprof(iw(n),ithread))
      call temporal_interpolation(vh1(1),vh1(2),vprof(iw(n),ithread))
      call temporal_interpolation(rho1(1),rho1(2),rhoprof(iw(n),ithread))
      call temporal_interpolation(rhograd1(1),rhograd1(2),rhogradprof(iw(n),ithread))

      indzindicator(iw(n),ithread)=.false.
    endif
  end do
end subroutine interpol_pbl_misslev

subroutine interpol_pbl_short(zt,rhoa,rhograd,ithread)
  implicit none 

  integer,intent(in)  :: ithread ! number of OMP thread starting at 1
  real, intent(in)    :: zt
  real, intent(inout) :: rhoa,rhograd
  real                :: dz1,dz2

  call find_vert_vars(height,zt,interp_state%indz,dz1,dz2,interp_state%lbounds,.false.)

  call vert_interpol(wprof(interp_state%indz,ithread),wprof(interp_state%indzp,ithread),dz1,dz2,interp_state%w)
  call vert_interpol(uprof(interp_state%indz,ithread),uprof(interp_state%indzp,ithread),dz1,dz2,interp_state%u)
  call vert_interpol(vprof(interp_state%indz,ithread),vprof(interp_state%indzp,ithread),dz1,dz2,interp_state%v)
  call vert_interpol(rhoprof(interp_state%indz,ithread),rhoprof(interp_state%indzp,ithread),dz1,dz2,rhoa)
  call vert_interpol(rhogradprof(interp_state%indz,ithread),rhogradprof(interp_state%indzp,ithread),dz1,dz2,rhograd)
end subroutine interpol_pbl_short

subroutine interpol_mesoscale(xt,yt,zt,zteta)

  use turbulence_mod

  real, intent(in)    :: xt,yt,zt,zteta
#ifdef ETA
  integer             :: iuv(2),iweta(2)
#endif
  integer             :: iw(2)

  ! Where in the grid? Stereographic (interp_state%ngrid<0) or nested (interp_state%ngrid>0)
  !***************************************************************
  call find_ngrid(xt,yt)

  call find_grid_indices(xt,yt)

  ! Determine the level below the current position
  !***********************************************
  call find_z_level_meters(zt)
  iw(:)=(/ interp_state%indz, interp_state%indzp /)
  
#ifdef ETA
  call find_z_level_eta(zteta)
  iuv(:)=(/ interp_state%induv, interp_state%indpuv /)
  iweta(:)=(/ interp_state%indzeta, interp_state%indzpeta /)
  call stdev_eta(iw,iuv,iweta)
#else
  iw(:)=(/ interp_state%indz, interp_state%indzp /)
  call stdev_meter(iw)
#endif

end subroutine interpol_mesoscale

subroutine interpol_wind(itime,xt,yt,zt,zteta)
  !                           i   i  i  i

  !*****************************************************************************
  !                                                                            *
  !  This subroutine interpolates the wind data to current trajectory position.*
  !                                                                            *
  !    Author: A. Stohl                                                        *
  !                                                                            *
  !    16 December 1997                                                        *
  !                                                                            *
  !  Revision March 2005 by AST : all output variables in common block cal-    *
  !                               culation of standard deviation done in this  *
  !                               routine rather than subroutine call in order *
  !                               to save computation time                     *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! interp_state%u,interp_state%v,interp_state%w              wind components                                         *
  ! itime [s]          current temporal position                               *
  ! memtime(3) [s]     times of the wind fields in memory                      *
  ! xt,yt,zt           coordinates position for which wind data shall be       *
  !                    calculated                                              *
  !                                                                            *
  ! Constants:                                                                 *
  !                                                                            *
  !*****************************************************************************

  integer, intent(in) :: itime
  real, intent(in)    :: xt,yt,zt,zteta
#ifdef ETA
  integer             :: iuv(2),iweta(2)
#else
  integer             :: iw(2)
#endif

  ! Where in the grid? Stereographic (interp_state%ngrid<0) or nested (interp_state%ngrid>0)
  !***************************************************************
  call find_ngrid(xt,yt)

  call find_grid_indices(xt,yt)
  ! ! Multilinear interpolation in time and space
  ! !********************************************

  ! Determine the lower left corner and its distance to the current position
  !*************************************************************************
  call find_grid_distances(xt,yt)

  ! Calculate variables for time interpolation
  !*******************************************
  call find_time_vars(itime)

  ! Interpolate over the windfields depending on the prefered
  ! coordinate system
  !**********************************************************
#ifdef ETA
  ! Same for eta coordinates
  !*************************
  call find_z_level_eta(zteta)

  iuv(:)  = (/ interp_state%induv, interp_state%indpuv /)
  iweta(:)= (/ interp_state%indzeta, interp_state%indzpeta /)
  call interpol_wind_eta(zteta,iuv,iweta)
  !call stdev_wind_eta(iw,iuv,iweta)
#else
  ! Determine the level below the current position for interp_state%u,interp_state%v
  !*******************************************************
  call find_z_level_meters(zt)

  iw(:)=(/ interp_state%indz, interp_state%indzp /)
  call interpol_wind_meter(zt,iw)
  !call stdev_wind_meter(iw)
#endif

end subroutine interpol_wind

subroutine interpol_wind_short(itime,xt,yt,zt,zteta)
!                                i   i  i  i  i

  !*****************************************************************************
  !                                                                            *
  !  This subroutine interpolates the wind data to current trajectory position.*
  !                                                                            *
  !    Author: A. Stohl                                                        *
  !                                                                            *
  !    16 December 1997                                                        *
  !                                                                            *
  !  Revision March 2005 by AST : all output variables in common block         *
  !                                                                            *
  !*****************************************************************************
  !                                                                            *
  ! Variables:                                                                 *
  ! interp_state%u,interp_state%v,interp_state%w              wind components                                         *
  ! itime [s]          current temporal position                               *
  ! memtime(3) [s]     times of the wind fields in memory                      *
  ! xt,yt,zt           coordinates position for which wind data shall be       *
  !                    calculated                                              *
  !                                                                            *
  ! Constants:                                                                 *
  !                                                                            *
  !*****************************************************************************

  integer, intent(in) :: itime
  real, intent(in) :: xt,yt,zt,zteta
#ifdef ETA
  integer             :: iuv(2),iweta(2)
#else
  integer             :: iw(2)
#endif

  !********************************************
  ! Multilinear interpolation in time and space
  !********************************************

  ! Where in the grid? Stereographic (interp_state%ngrid<0) or nested (interp_state%ngrid>0)
  !***************************************************************
  call find_ngrid(xt,yt)
  call find_grid_indices(xt,yt)
  call find_grid_distances(xt,yt)

  ! Calculate variables for time interpolation
  !*******************************************
  call find_time_vars(itime)

  ! Interpolate over the windfields depending on the prefered
  ! coordinate system
  !**********************************************************
#ifdef ETA
  ! Determine the level below the current position for eta coordinates
  !*******************************************************************
  call find_z_level_eta(zteta)

  iuv(:)=(/ interp_state%induv, interp_state%indpuv /)
  iweta(:)=(/ interp_state%indzeta, interp_state%indzpeta /)
  ! Interpolate the interp_state%u, interp_state%v, interp_state%weta windfields
  !**************************************
  call interpol_wind_eta(zteta,iuv,iweta)
#else

  ! Determine the level below the current position for interp_state%u,interp_state%v
  !*******************************************************
  call find_z_level_meters(zt)

  iw(:)=(/ interp_state%indz, interp_state%indzp /)
  call interpol_wind_meter(zt,iw)
#endif

end subroutine interpol_wind_short

subroutine interpol_partoutput_val(fieldname,output,j)
  integer, intent(in)         :: j          ! particle number
  character(2), intent(in)    :: fieldname  ! input field to interpolate over
  real, intent(inout)         :: output

  ! Interpolate over the windfields depending on the prefered
  ! coordinate system
  !**********************************************************
#ifdef ETA
  call interpol_partoutput_val_eta(fieldname,output,j)
#else
  call interpol_partoutput_val_meter(fieldname,output,j)
#endif
end subroutine interpol_partoutput_val

subroutine interpol_htropo_hmix(tropop,h)

  real, intent(inout) :: tropop   ! height of troposphere
  real, intent(inout) :: h        ! mixing height
  real    :: h1(2)                ! mixing height of 2 timesteps
  integer :: mind                 ! windfield index
  integer :: i,j,k,m              ! loop variables

  h=0.
  if (interp_state%ngrid.le.0) then
    if (interpolhmix) then
      do m=1,2
        call hor_interpol(hmix,h1(m),1,memind(m),1)
      end do
    else
      do k=1,2
        mind=memind(k) ! eso: compatibility with 3-field version
        do j=interp_state%jy,interp_state%jyp
          do i=interp_state%ix,interp_state%ixp
             if (hmix(i,j,1,mind).gt.h) h=hmix(i,j,1,mind)
          end do
        end do
      end do
    endif
    tropop=tropopause(interp_state%nix,interp_state%njy,1,memind(1))
  else
    do k=1,2
      mind=memind(k)
      do j=interp_state%jy,interp_state%jyp
        do i=interp_state%ix,interp_state%ixp
          if (hmixn(i,j,1,mind,interp_state%ngrid).gt.h) h=hmixn(i,j,1,mind,interp_state%ngrid)
        end do
      end do
    end do
    tropop=tropopausen(interp_state%nix,interp_state%njy,1,memind(1),interp_state%ngrid)
  endif

  if (interpolhmix) h= (h1(1)*interp_state%dt2 + h1(2)*interp_state%dt1)*interp_state%dtt 

end subroutine interpol_htropo_hmix

subroutine interpol_density(itime,ipart,output)

  integer, intent(in) :: itime,ipart  ! time and particle index
  real, intent(inout) :: output ! output density (rhoi)
  integer :: ind
  real :: dz1,dz2,rhoprof(2)

  ! Where in the grid? Stereographic (interp_state%ngrid<0) or nested (interp_state%ngrid>0)
  !***************************************************************
  call find_ngrid(part(ipart)%xlon,part(ipart)%ylat)
  call find_grid_indices(real(part(ipart)%xlon),real(part(ipart)%ylat))
  call find_grid_distances(real(part(ipart)%xlon),real(part(ipart)%ylat))
  call find_time_vars(itime)

  ! Take density from 2nd wind field in memory 
  !(accurate enough, no time interpolation needed)
  !***********************************************
  
#ifdef ETA
  call find_z_level_eta(real(part(ipart)%zeta))
  call find_vert_vars(uvheight,real(part(ipart)%zeta),interp_state%induv, &
    dz1,dz2,interp_state%lbounds_uv,.false.)
  if (interp_state%ngrid.le.0) then
    do ind=interp_state%induv,interp_state%indpuv
      call hor_interpol(rhoeta,rhoprof(ind-interp_state%induv+1),ind,memind(2),nzmax)
    end do
  else
    do ind=interp_state%induv,interp_state%indpuv
      call hor_interpol_nest(rhoetan,rhoprof(ind-interp_state%induv+1),ind,memind(2), &
        nzmax)
    end do
  endif
#else
  call find_z_level_meters(real(part(ipart)%z))
  call find_vert_vars(height,real(part(ipart)%z),interp_state%indz, &
    dz1,dz2,interp_state%lbounds,.false.)
  if (interp_state%ngrid.le.0) then
    do ind=interp_state%indz,interp_state%indzp
      call hor_interpol(rho,rhoprof(ind-interp_state%indz+1),ind,memind(2),nzmax)
    end do
  else
    do ind=interp_state%indz,interp_state%indzp
      call hor_interpol_nest(rhon,rhoprof(ind-interp_state%indz+1),ind,memind(2),nzmax)
    end do
  endif
#endif
  call vert_interpol(rhoprof(1),rhoprof(2),dz1,dz2,output)
end subroutine interpol_density

subroutine interpol_rain(itime,kz,yint1,yint2,yint3,ytint,yint4,intiy1,intiy2,icmv)
  !                       i     i   o     o     o     o     o     o      o     i   
  !****************************************************************************
  !                                                                           *
  !  Interpolation of meteorological fields on 2-d model layers.              *
  !  In horizontal direction bilinear interpolation is used.                  *
  !  Temporally a linear interpolation is used.                               *
  !  Seven fields are interpolated at the same time.                          *
  !                                                                           *
  !  This is a special version of levlininterpol to save CPU time.            *
  !                                                                           *
  !  1 first time                                                             *
  !  2 second time                                                            *
  !                                                                           *
  !                                                                           *
  !     Author: A. Stohl                                                      *
  !                                                                           *
  !     30 August 1996                                                        *
  !                                                                           *
  !                                                                           *
  ! PS, AP 04/2019, 11/2020:                                                  *
  !                 put back temporal interpolation of rain, from v10.01      *
  !      and cloud bottom / thickness interpolation                           *
  ! PS, AP 01/2021:                                                           *
  !      interpolate particle temperature and cloud total water               *
  ! PS, AP 02/2021:                                                           *
  !      interpolation of precipitation using two additional fields           *
  !      which are temporally equidistant between the main fields             *
  !                                                                           *
  !****************************************************************************
  !                                                                           *
  ! Variables:                                                                *
  !                                                                           *
  ! interp_state%dt1,interp_state%dt2              time differences between fields and current position *
  ! dz1,dz2              z distance between levels and current position       *
  ! height(nzmax)        heights of the model levels                          *
  ! mm                   help variable                                        *
  ! interp_state%indz                 the level closest to the current trajectory position *
  ! indzh                help variable                                        *
  ! itime                current time                                         *
  ! interp_state%ix,interp_state%jy                x,y coordinates of lower left subgrid point          *
  ! level                level at which interpolation shall be done 2d, =1    *
  ! kz                   level at which interpolation shall be done           *
  ! memind(3)            points to the places of the wind fields              *
  ! nx,ny                actual field dimensions in x,y and z direction       *
  ! nxmax,nymax,nzmax    maximum field dimensions in x,y and z direction      *
  ! xt                   current x coordinate                                 *
  ! yint                 the final interpolated value                         *
  ! yt                   current y coordinate                                 *
  ! yy?(0:nxmax,0:nymax,nzx2d,3) meteorological field used for interpolation  *
  ! yyt(0:nxmax,0:nymax,nzmax,3) tt field                                     * 
  ! iy1,iy2(0:nxmax,0:nymax,3) cloud bottom, thickness fields (integer)       *
  ! zt                   current z coordinate                                 *
  !                                                                           *
  !****************************************************************************
  use par_mod, only: numwfmem, numpf
  use com_mod, only: lcw

  implicit none

  integer, intent(in) :: kz, icmv, itime
  integer, intent(out) :: intiy1,intiy2
  real, intent(out) :: yint1,yint2,yint3,ytint,yint4
  integer :: m
  integer :: mm
  real :: ip1,ip2,ip3,ip4,ipsum
  real :: dt,dtp1,dtp2,rt
  real :: y1(2),y2(2),y3(2),y4(2),yi1(2),yi2(2),ytt(2) ! interpolated values
  
  integer, dimension(2) :: ip, mp

  !**********************************************************************
  ! 1.) Bilinear horizontal interpolation
  ! This has to be done separately for 2 fields (Temporal)
  !*******************************************************
  ! Loop over 2 time steps
  !***********************

  !-------------------------------------------------------------------------
  ! PS, AT new interpolation of precip with 2 additional fields
  ! therefore, we need a special treatment of lsp,cp which are in yy1,yy2
  !-------------------------------------------------------------------------
  !
  !      1.1 1.2 1.3               ip(1).mp(1)
  !      1.2 1.3 2.1               ip(2).mp(2)
  !
  !   ||___|___|___||___|___|___||
  !
  ! ip  1   2   3    1   2   3    1
  ! m        1            2  
  !
  !-------------------------------------------------------------------------

  interp_state%dt1 = real(itime  - memtime(1))
  interp_state%dt2 = real(memtime(2) - itime)
  dt  = real(memtime(2) - memtime(1))
  if (dt.eq.0. .and. interp_state%dt1.eq.0.) then ! Fix if last last timestep and memtime(2)=memtime(1)
    dt = 1.
    interp_state%dt2 = 1.
  endif
  interp_state%dtt = dt/3.
  if (numpf .eq. 1) then
    mp(1) = 1
    mp(2) = 2
    ip(1) = 1
    ip(2) = 1
    dtp1 = interp_state%dt1
    dtp2 = interp_state%dt2
  else
    rt = abs(interp_state%dt1/dt)
    if (0 .le. rt .and. rt .lt. 1./3.) then
      mp(1) = 1
      mp(2) = 1
      ip(1) = 1
      ip(2) = 2
      dtp1 = interp_state%dt1
      dtp2 = interp_state%dt2 - 2.*interp_state%dtt
    elseif (1./3. .le. rt .and.  rt .lt. 2./3.) then
      mp(1) = 1
      mp(2) = 1
      ip(1) = 2
      ip(2) = 3
      dtp1 = interp_state%dt1 - interp_state%dtt
      dtp2 = interp_state%dt2 - interp_state%dtt
    elseif (2./3. .le. rt .and.  rt .lt. 1.) then
      mp(1) = 1
      mp(2) = 2
      ip(1) = 3
      ip(2) = 1
      dtp1 = interp_state%dt1 - 2.*interp_state%dtt
      dtp2 = interp_state%dt2
    endif
  endif


  if (interp_state%ngrid.le.0) then ! No nest
    do m=1,2
      mm=memind(mp(m))
      y1(m)= interp_state%p1*lsprec(interp_state%ix ,interp_state%jy ,1,ip(m),mm) &
           + interp_state%p2*lsprec(interp_state%ixp,interp_state%jy ,1,ip(m),mm) &
           + interp_state%p3*lsprec(interp_state%ix ,interp_state%jyp,1,ip(m),mm) &
           + interp_state%p4*lsprec(interp_state%ixp,interp_state%jyp,1,ip(m),mm)
      y2(m)= interp_state%p1*convprec(interp_state%ix ,interp_state%jy ,1,ip(m),mm) &
           + interp_state%p2*convprec(interp_state%ixp,interp_state%jy ,1,ip(m),mm) &
           + interp_state%p3*convprec(interp_state%ix ,interp_state%jyp,1,ip(m),mm) &
           + interp_state%p4*convprec(interp_state%ixp,interp_state%jyp,1,ip(m),mm)

      mm=memind(m)
      y3(m)= interp_state%p1*tcc(interp_state%ix ,interp_state%jy ,1,mm) &
           + interp_state%p2*tcc(interp_state%ixp,interp_state%jy ,1,mm) &
           + interp_state%p3*tcc(interp_state%ix ,interp_state%jyp,1,mm) &
           + interp_state%p4*tcc(interp_state%ixp,interp_state%jyp,1,mm)
#ifdef ETA
      ytt(m)=interp_state%p1*tteta(interp_state%ix ,interp_state%jy ,kz,mm) &
           + interp_state%p2*tteta(interp_state%ixp,interp_state%jy ,kz,mm) &
           + interp_state%p3*tteta(interp_state%ix ,interp_state%jyp,kz,mm) &
           + interp_state%p4*tteta(interp_state%ixp,interp_state%jyp,kz,mm)
#else
      ytt(m)=interp_state%p1*tt(interp_state%ix ,interp_state%jy ,kz,mm) &
           + interp_state%p2*tt(interp_state%ixp,interp_state%jy ,kz,mm) &
           + interp_state%p3*tt(interp_state%ix ,interp_state%jyp,kz,mm) &
           + interp_state%p4*tt(interp_state%ixp,interp_state%jyp,kz,mm)
#endif
      if (lcw) &
        y4(m)= interp_state%p1*ctwc(interp_state%ix ,interp_state%jy ,mm) &
           + interp_state%p2*ctwc(interp_state%ixp,interp_state%jy ,mm) &
           + interp_state%p3*ctwc(interp_state%ix ,interp_state%jyp,mm) &
           + interp_state%p4*ctwc(interp_state%ixp,interp_state%jyp,mm)

  !PS clouds:
      ip1=1.
      ip2=1.
      ip3=1.
      ip4=1.
      ipsum=1.
      if (icloudbot(interp_state%ix ,interp_state%jy ,mm) .eq. icmv) then
        ip1=0.
        ipsum=ipsum-interp_state%p1
      endif
      if (icloudbot(interp_state%ixp,interp_state%jy ,mm) .eq. icmv) then
        ip2=0.
        ipsum=ipsum-interp_state%p2
      endif
      if (icloudbot(interp_state%ix ,interp_state%jyp,mm) .eq. icmv) then
        ip3=0.
        ipsum=ipsum-interp_state%p3
      endif
      if (icloudbot(interp_state%ixp,interp_state%jyp,mm) .eq. icmv) then
        ip4=0.
        ipsum=ipsum-interp_state%p4
      endif
      if (ipsum .eq. 0.) then
        yi1(m)=icmv
      else
        yi1(m)=(ip1*interp_state%p1*icloudbot(interp_state%ix ,interp_state%jy ,mm) &
              + ip2*interp_state%p2*icloudbot(interp_state%ixp,interp_state%jy ,mm) &
              + ip3*interp_state%p3*icloudbot(interp_state%ix ,interp_state%jyp,mm) &
              + ip4*interp_state%p4*icloudbot(interp_state%ixp,interp_state%jyp,mm))/ipsum
        ! AP test output
  !      if (yi1(m) .lt. 1.) then
  !        write(*,*) ip1,ip2,ip3,ip4,ipsum
  !        write(*,*) interp_state%p1,interp_state%p2,interp_state%p3,interp_state%p4
  !        write(*,*) iy1(interp_state%ix ,interp_state%jy ,mm), iy1(interp_state%ixp,interp_state%jy ,mm),  iy1(interp_state%ix ,interp_state%jyp,mm), iy1(interp_state%ixp,interp_state%jyp,mm)
  !      endif            
              
      endif
          
      ip1=1.
      ip2=1.
      ip3=1.
      ip4=1.
      ipsum=1.
      if (icloudtop(interp_state%ix ,interp_state%jy ,mm) .eq. icmv) then
        ip1=0.
        ipsum=ipsum-interp_state%p1
      endif
      if (icloudtop(interp_state%ixp,interp_state%jy ,mm) .eq. icmv) then
        ip2=0.
        ipsum=ipsum-interp_state%p2
      endif
      if (icloudtop(interp_state%ix ,interp_state%jyp,mm) .eq. icmv) then
        ip3=0.
        ipsum=ipsum-interp_state%p3
      endif
      if (icloudtop(interp_state%ixp,interp_state%jyp,mm) .eq. icmv) then
        ip4=0.
        ipsum=ipsum-interp_state%p4
      endif
      if (ipsum .eq. 0.) then
        yi2(m)=icmv
      else
        yi2(m)=(ip1*interp_state%p1*icloudtop(interp_state%ix ,interp_state%jy ,mm) &
              + ip2*interp_state%p2*icloudtop(interp_state%ixp,interp_state%jy ,mm) &
              + ip3*interp_state%p3*icloudtop(interp_state%ix ,interp_state%jyp,mm) &
              + ip4*interp_state%p4*icloudtop(interp_state%ixp,interp_state%jyp,mm))/ipsum
      endif
  !PS end clouds
    end do
  else ! Nest
    do m=1,2
      mm=memind(mp(m))
      y1(m)= interp_state%p1*lsprecn(interp_state%ix ,interp_state%jy ,1,ip(m),mm,interp_state%ngrid) &
           + interp_state%p2*lsprecn(interp_state%ixp,interp_state%jy ,1,ip(m),mm,interp_state%ngrid) &
           + interp_state%p3*lsprecn(interp_state%ix ,interp_state%jyp,1,ip(m),mm,interp_state%ngrid) &
           + interp_state%p4*lsprecn(interp_state%ixp,interp_state%jyp,1,ip(m),mm,interp_state%ngrid)
      y2(m)= interp_state%p1*convprecn(interp_state%ix ,interp_state%jy ,1,ip(m),mm,interp_state%ngrid) &
           + interp_state%p2*convprecn(interp_state%ixp,interp_state%jy ,1,ip(m),mm,interp_state%ngrid) &
           + interp_state%p3*convprecn(interp_state%ix ,interp_state%jyp,1,ip(m),mm,interp_state%ngrid) &
           + interp_state%p4*convprecn(interp_state%ixp,interp_state%jyp,1,ip(m),mm,interp_state%ngrid)

      mm=memind(m)
      y3(m)= interp_state%p1*tccn(interp_state%ix ,interp_state%jy ,1,mm,interp_state%ngrid) &
           + interp_state%p2*tccn(interp_state%ixp,interp_state%jy ,1,mm,interp_state%ngrid) &
           + interp_state%p3*tccn(interp_state%ix ,interp_state%jyp,1,mm,interp_state%ngrid) &
           + interp_state%p4*tccn(interp_state%ixp,interp_state%jyp,1,mm,interp_state%ngrid)
#ifdef ETA
      ytt(m)=interp_state%p1*ttetan(interp_state%ix ,interp_state%jy ,kz,mm,interp_state%ngrid) &
           + interp_state%p2*ttetan(interp_state%ixp,interp_state%jy ,kz,mm,interp_state%ngrid) &
           + interp_state%p3*ttetan(interp_state%ix ,interp_state%jyp,kz,mm,interp_state%ngrid) &
           + interp_state%p4*ttetan(interp_state%ixp,interp_state%jyp,kz,mm,interp_state%ngrid)
#else
      ytt(m)=interp_state%p1*ttn(interp_state%ix ,interp_state%jy ,kz,mm,interp_state%ngrid) &
           + interp_state%p2*ttn(interp_state%ixp,interp_state%jy ,kz,mm,interp_state%ngrid) &
           + interp_state%p3*ttn(interp_state%ix ,interp_state%jyp,kz,mm,interp_state%ngrid) &
           + interp_state%p4*ttn(interp_state%ixp,interp_state%jyp,kz,mm,interp_state%ngrid)
#endif
      if (lcw_nest(interp_state%ngrid)) &
        y4(m)= interp_state%p1*ctwcn(interp_state%ix ,interp_state%jy ,mm,interp_state%ngrid) &
           + interp_state%p2*ctwcn(interp_state%ixp,interp_state%jy ,mm,interp_state%ngrid) &
           + interp_state%p3*ctwcn(interp_state%ix ,interp_state%jyp,mm,interp_state%ngrid) &
           + interp_state%p4*ctwcn(interp_state%ixp,interp_state%jyp,mm,interp_state%ngrid)

  !PS clouds:
      ip1=1.
      ip2=1.
      ip3=1.
      ip4=1.
      ipsum=1.
      if (icloudbotn(interp_state%ix ,interp_state%jy ,mm,interp_state%ngrid) .eq. icmv) then
        ip1=0.
        ipsum=ipsum-interp_state%p1
      endif
      if (icloudbotn(interp_state%ixp,interp_state%jy ,mm,interp_state%ngrid) .eq. icmv) then
        ip2=0.
        ipsum=ipsum-interp_state%p2
      endif
      if (icloudbotn(interp_state%ix ,interp_state%jyp,mm,interp_state%ngrid) .eq. icmv) then
        ip3=0.
        ipsum=ipsum-interp_state%p3
      endif
      if (icloudbotn(interp_state%ixp,interp_state%jyp,mm,interp_state%ngrid) .eq. icmv) then
        ip4=0.
        ipsum=ipsum-interp_state%p4
      endif
      if (ipsum .eq. 0.) then
        yi1(m)=icmv
      else
        yi1(m)=(ip1*interp_state%p1*icloudbotn(interp_state%ix ,interp_state%jy ,mm,interp_state%ngrid) &
              + ip2*interp_state%p2*icloudbotn(interp_state%ixp,interp_state%jy ,mm,interp_state%ngrid) &
              + ip3*interp_state%p3*icloudbotn(interp_state%ix ,interp_state%jyp,mm,interp_state%ngrid) &
              + ip4*interp_state%p4*icloudbotn(interp_state%ixp,interp_state%jyp,mm,interp_state%ngrid))/ipsum
      endif
          
      ip1=1.
      ip2=1.
      ip3=1.
      ip4=1.
      ipsum=1.
      if (icloudtopn(interp_state%ix ,interp_state%jy ,mm,interp_state%ngrid) .eq. icmv) then
        ip1=0.
        ipsum=ipsum-interp_state%p1
      endif
      if (icloudtopn(interp_state%ixp,interp_state%jy ,mm,interp_state%ngrid) .eq. icmv) then
        ip2=0.
        ipsum=ipsum-interp_state%p2
      endif
      if (icloudtopn(interp_state%ix ,interp_state%jyp,mm,interp_state%ngrid) .eq. icmv) then
        ip3=0.
        ipsum=ipsum-interp_state%p3
      endif
      if (icloudtopn(interp_state%ixp,interp_state%jyp,mm,interp_state%ngrid) .eq. icmv) then
        ip4=0.
        ipsum=ipsum-interp_state%p4
      endif
      if (ipsum .eq. 0.) then
        yi2(m)=icmv
      else
        yi2(m)=(ip1*interp_state%p1*icloudtopn(interp_state%ix ,interp_state%jy ,mm,interp_state%ngrid) &
              + ip2*interp_state%p2*icloudtopn(interp_state%ixp,interp_state%jy ,mm,interp_state%ngrid) &
              + ip3*interp_state%p3*icloudtopn(interp_state%ix ,interp_state%jyp,mm,interp_state%ngrid) &
              + ip4*interp_state%p4*icloudtopn(interp_state%ixp,interp_state%jyp,mm,interp_state%ngrid))/ipsum
      endif
  !PS end clouds
    end do
  endif

  !************************************
  ! 2.) Temporal interpolation (linear)
  !************************************

  yint1=(y1(1)*dtp2+y1(2)*dtp1)/interp_state%dtt ! lsp
  yint2=(y2(1)*dtp2+y2(2)*dtp1)/interp_state%dtt ! cp
  
  yint3=(y3(1)*interp_state%dt2+y3(2)*interp_state%dt1)/dt
  yint4=(y4(1)*interp_state%dt2+y4(2)*interp_state%dt1)/dt
  ytint=(ytt(1)*interp_state%dt2+ytt(2)*interp_state%dt1)/dt

!PS clouds:450.

!  write(*,*) yi1(1),yi1(2),yi2(1),yi2(2),dt,interp_state%dt1,interp_state%dt2
  intiy1=int((yi1(1)*interp_state%dt2 + yi1(2)*interp_state%dt1)/dt)
  if (int(yi1(1)) .eq. icmv) intiy1=int(yi1(2))
  if (int(yi1(2)) .eq. icmv) intiy1=int(yi1(1))

  intiy2=int((yi2(1)*interp_state%dt2 + yi2(2)*interp_state%dt1)/dt)
  if (int(yi2(1)) .eq. icmv) intiy2=int(yi2(2))
  if (int(yi2(2)) .eq. icmv) intiy2=int(yi2(1))
  
!  write(*,*) 'before cbot: ', intiy1, ' cthick: ', intiy2   
  if (intiy1 .ne. icmv .and. intiy2 .ne. icmv) then
    intiy2 = intiy2 !intiy1 + intiy2 ! convert cloud thickness to cloud top
  else
    intiy1=icmv
    intiy2=icmv
  endif
  if (intiy2 .ne. icmv .and. intiy2 .lt. 0) then
    write(*,*) itime, memind(1), memind(2)
    write(*,*) yi1(1),yi1(2),yi2(1),yi2(2),dt,interp_state%dt1,interp_state%dt2
    write(*,*) 'final cbot: ', intiy1, ' ctop: ', intiy2
    stop 'intiy2 (cloud top) negative'
  endif
!PS end clouds

end subroutine interpol_rain

!*********************
!* PRIVATE FUNCTIONS *
!*********************
! Interpolation of wind fields
!*****************************
#ifdef ETA
subroutine interpol_wind_eta(zteta,iuv,iweta)

!* PRIVATE FUNCTION *

  real, intent(in)    :: zteta
  integer,intent(in)  :: iuv(2),iweta(2)
  integer             :: n,m
  real                :: uh(2),vh(2),wetah(2),uh1(2),vh1(2),wetah1(2)
  real                :: dz1uv,dz2uv,dz1weta,dz2weta

  !**********************************************************************
  ! 1.) Bilinear horizontal interpolation
  ! This has to be done separately for 6 fields (Temporal(2)*Vertical(3))
  !**********************************************************************

  ! Vertical distance to the level below and above current position
  !****************************************************************
  call find_vert_vars(uvheight,zteta,interp_state%induv,dz1uv,dz2uv,interp_state%lbounds_uv,.false.)
  call find_vert_vars(wheight,zteta,interp_state%indzeta,dz1weta,dz2weta,interp_state%lbounds_w,.true.)

  ! Loop over 2 time steps and 2 levels
  !************************************
  if (interp_state%ngrid.le.0) then ! No nest
    do m=1,2
      do n=1,2
        call hor_interpol(wweta,wetah1(n),iweta(n),memind(m),nzmax)
        if (interp_state%ngrid.lt.0) then
          call hor_interpol(uupoleta,uh1(n),iuv(n),memind(m),nzmax)
          call hor_interpol(vvpoleta,vh1(n),iuv(n),memind(m),nzmax)
        else
          call hor_interpol(uueta,uh1(n),iuv(n),memind(m),nzmax)
          call hor_interpol(vveta,vh1(n),iuv(n),memind(m),nzmax)
        endif
      end do
      call vert_interpol(uh1(1),uh1(2),dz1uv,dz2uv,uh(m))
      call vert_interpol(vh1(1),vh1(2),dz1uv,dz2uv,vh(m))
      call vert_interpol(wetah1(1),wetah1(2),dz1weta,dz2weta,wetah(m))
    end do 
  else ! Nest
    do m=1,2
      do n=1,2
        
        ! wetah1(n) = interp_state%p1*wwetan(interp_state%ix ,interp_state%jy ,iweta(n),memind(m),interp_state%ngrid) &
        !           + interp_state%p2*wwetan(interp_state%ixp,interp_state%jy ,iweta(n),memind(m),interp_state%ngrid) &
        !           + interp_state%p3*wwetan(interp_state%ix ,interp_state%jyp,iweta(n),memind(m),interp_state%ngrid) &
        !           + interp_state%p4*wwetan(interp_state%ixp,interp_state%jyp,iweta(n),memind(m),interp_state%ngrid)
        call hor_interpol_nest(wwetan,wetah1(n),iweta(n),memind(m),nzmax)
        call hor_interpol_nest(uuetan,uh1(n),iuv(n),memind(m),nzmax)
        call hor_interpol_nest(vvetan,vh1(n),iuv(n),memind(m),nzmax)
      end do
      call vert_interpol(uh1(1),uh1(2),dz1uv,dz2uv,uh(m))
      call vert_interpol(vh1(1),vh1(2),dz1uv,dz2uv,vh(m))
      call vert_interpol(wetah1(1),wetah1(2),dz1weta,dz2weta,wetah(m))
    end do    
  endif
  call temporal_interpolation(uh(1),uh(2),interp_state%u)
  call temporal_interpolation(vh(1),vh(2),interp_state%v)
  call temporal_interpolation(wetah(1),wetah(2),interp_state%weta)
end subroutine interpol_wind_eta
#else

subroutine interpol_wind_meter(zt,iw)

!* PRIVATE FUNCTION *

  real, intent(in)    :: zt
  integer,intent(in)  :: iw(2)
  integer             :: n,m
  real                :: uh(2),vh(2),wh(2),uh1(2),vh1(2),wh1(2)
  real                :: dz1w,dz2w

  !**********************************************************************
  ! 1.) Bilinear horizontal interpolation
  ! This has to be done separately for 6 fields (Temporal(2)*Vertical(3))
  !**********************************************************************

  ! Vertical distance to the level below and above current position
  !****************************************************************
  call find_vert_vars(height,zt,interp_state%indz,dz1w,dz2w,interp_state%lbounds,.false.)

  ! Loop over 2 time steps and 2 levels
  !************************************
  if (interp_state%ngrid.le.0) then ! No nest
    do m=1,2
      do n=1,2
        call hor_interpol(ww,wh1(n),iw(n),memind(m),nzmax)
        if (interp_state%ngrid.lt.0) then
          call hor_interpol(uupol,uh1(n),iw(n),memind(m),nzmax)
          call hor_interpol(vvpol,vh1(n),iw(n),memind(m),nzmax)
        else
          call hor_interpol(uu,uh1(n),iw(n),memind(m),nzmax)
          call hor_interpol(vv,vh1(n),iw(n),memind(m),nzmax)
        endif
      end do
      call vert_interpol(wh1(1),wh1(2),dz1w,dz2w,wh(m))
      call vert_interpol(uh1(1),uh1(2),dz1w,dz2w,uh(m))
      call vert_interpol(vh1(1),vh1(2),dz1w,dz2w,vh(m))
    end do 
  else ! Nest
    do m=1,2
      do n=1,2
        call hor_interpol_nest(wwn,wh1(n),iw(n),memind(m),nzmax)
        call hor_interpol_nest(uun,uh1(n),iw(n),memind(m),nzmax)
        call hor_interpol_nest(vvn,vh1(n),iw(n),memind(m),nzmax)
      end do
      call vert_interpol(wh1(1),wh1(2),dz1w,dz2w,wh(m))
      call vert_interpol(uh1(1),uh1(2),dz1w,dz2w,uh(m))
      call vert_interpol(vh1(1),vh1(2),dz1w,dz2w,vh(m))
    end do    
  endif
  call temporal_interpolation(wh(1),wh(2),interp_state%w)
  call temporal_interpolation(uh(1),uh(2),interp_state%u)
  call temporal_interpolation(vh(1),vh(2),interp_state%v)
end subroutine interpol_wind_meter
#endif

#ifdef ETA
subroutine interpol_partoutput_val_eta(fieldname,output,j)
  implicit none

  integer, intent(in)         :: j          ! particle number
  character(2), intent(in)    :: fieldname  ! input field to interpolate over
  real, intent(inout)         :: output
  real                        :: field1(2)

  if (int(interp_state%dz1out).eq.-1) then
    call find_z_level_eta(real(part(j)%zeta))
    call find_vert_vars(uvheight,real(part(j)%zeta),interp_state%induv,interp_state%dz1out,interp_state%dz2out, &
      interp_state%lbounds_uv,.false.)
  endif

  select case(fieldname)
    case('PR','pr')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(prseta,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(prsetan,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('PV','pv')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(pveta,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(pvetan,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('QV','qv')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(qv,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(qvn,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('TT','tt')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(tteta,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(ttetan,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('UU','uu')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(uueta,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(uuetan,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('VV','vv')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(vveta,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(vvetan,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('WW','ww')
      call find_z_level_meters(real(part(j)%z))
      call find_vert_vars(height,real(part(j)%z),interp_state%indz, &
        interp_state%dz1out,interp_state%dz2out,interp_state%lbounds, &
        .false.)
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(ww,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(wwn,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
      interp_state%dz1out = -1
    case('RH','rh')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(rhoeta,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(rhoetan,field1,interp_state%induv,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
  end select
end subroutine interpol_partoutput_val_eta
#else

subroutine interpol_partoutput_val_meter(fieldname,output,j)
  implicit none

!* PRIVATE FUNCTION *

  integer, intent(in)         :: j          ! particle number
  character(2), intent(in)    :: fieldname  ! input field to interpolate over
  real, intent(inout)         :: output
  real                        :: field1(2)

  if (int(interp_state%dz1out).eq.-1) then
    call find_z_level_meters(real(part(j)%z))
    call find_vert_vars(height,real(part(j)%z),interp_state%indz, &
      interp_state%dz1out,interp_state%dz2out,interp_state%lbounds,.false.)
  endif

  select case(fieldname)
    case('PR','pr')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(prs,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(prsn,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('PV','pv')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(pv,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(pvn,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('QV','qv')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(qv,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(qvn,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('TT','tt')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(tt,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(ttn,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('UU','uu')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(uu,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(uun,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('VV','vv')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(vv,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(vvn,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('WW','ww')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(ww,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(wwn,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
    case('RH','rh')
      if (interp_state%ngrid.le.0) then
        call bilin_spatial_interpol(rho,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      else
        call bilin_spatial_interpol_nest(rhon,field1,interp_state%indz,interp_state%dz1out,interp_state%dz2out,nzmax)
      endif
      call temporal_interpolation(field1(1),field1(2),output)
  end select
end subroutine interpol_partoutput_val_meter
#endif
! #ifdef ETA
! subroutine interpol_pbl_eta(zt,zteta,rhoa,rhograd,ithread)
  
!   integer,intent(in)  :: ithread
!   real, intent(in)    :: zt,zteta
!   real, intent(inout) :: rhoa,rhograd
!   real                :: dz1w,dz2w,dz1uv,dz2uv,dz1weta,dz2weta

!   call find_vert_vars(height,zt,interp_state%indz,dz1w,dz2w,interp_state%lbounds,.false.)
!   call find_vert_vars(uvheight,zteta,interp_state%induv,dz1uv,dz2uv,interp_state%lbounds_uv,.false.)
!   call find_vert_vars(wheight,zteta,interp_state%indzeta,dz1weta,dz2weta,interp_state%lbounds_w,.true.)

!   call vert_interpol(wprof(interp_state%indz,ithread),wprof(interp_state%indzp,ithread),dz1w,dz2w,interp_state%w)
!   call vert_interpol(uprof(interp_state%induv,ithread),uprof(interp_state%indpuv,ithread),dz1uv,dz2uv,interp_state%u)
!   call vert_interpol(vprof(interp_state%induv,ithread),vprof(interp_state%indpuv,ithread),dz1uv,dz2uv,interp_state%v)
!   call vert_interpol(rhoprof(interp_state%induv,ithread),rhoprof(interp_state%indpuv,ithread),dz1uv,dz2uv,rhoa)
!   call vert_interpol(rhogradprof(interp_state%induv,ithread),rhogradprof(interp_state%indpuv,ithread),dz1uv,dz2uv,rhograd)
!   call vert_interpol(wprofeta(interp_state%indzeta,ithread),wprofeta(interp_state%indzpeta,ithread),dz1weta,dz2weta,interp_state%weta)
! end subroutine interpol_pbl_eta
! #endif

#ifdef ETA
subroutine stdev_eta(iw,iuv,iweta)

!* PRIVATE FUNCTION *

  ! Standard deviation of surrounding grid points
  ! Only used in mesoscale turbulence calculations
  !***********************************************

  integer,intent(in)  :: iw(2),iuv(2),iweta(2)
  real :: wsl,wsq,usl,usq,vsl,vsq,wetasl,wetasq
  integer             :: n,m
  real,parameter      :: eps=1.0e-30
  
  ! Standard deviations
  !********************
  wsl=0.
  wsq=0.
  usl=0.
  usq=0.
  vsl=0.
  vsq=0.
  wetasl=0.
  wetasq=0.

  if (interp_state%ngrid.le.0) then ! No nest  
    do m=1,2
      do n=1,2
        call compute_sl_sq(ww,wsl,wsq,iw(n),memind(m),nzmax)
        call compute_sl_sq(wweta,wetasl,wetasq,iweta(n),memind(m),nzmax)
        if (interp_state%ngrid.lt.0) then
          call compute_sl_sq(uupoleta,usl,usq,iuv(n),memind(m),nzmax)
          call compute_sl_sq(vvpoleta,vsl,vsq,iuv(n),memind(m),nzmax)
        else
          call compute_sl_sq(uueta,usl,usq,iuv(n),memind(m),nzmax)
          call compute_sl_sq(vveta,vsl,vsq,iuv(n),memind(m),nzmax)
        endif
      end do
    end do
  else ! Nest
    do m=1,2
      do n=1,2
        call compute_sl_sq_nest(wwn,wsl,wsq,iw(n),memind(m),nzmax)
        call compute_sl_sq_nest(wwetan,wetasl,wetasq,iweta(n),memind(m),nzmax)
        call compute_sl_sq_nest(uuetan,usl,usq,iuv(n),memind(m),nzmax)
        call compute_sl_sq_nest(vvetan,vsl,vsq,iuv(n),memind(m),nzmax)
      end do
    end do
  endif

  call stdev(wsl,wsq,16.,interp_state%wsig)
  call stdev(usl,usq,16.,interp_state%usig)
  call stdev(vsl,vsq,16.,interp_state%vsig)
  call stdev(wetasl,wetasq,16.,interp_state%wsigeta)

end subroutine stdev_eta
#else

subroutine stdev_meter(iw)

!* PRIVATE FUNCTION *

  ! Standard deviation of surrounding grid points
  ! Only used in mesoscale turbulence calculations
  !***********************************************

  integer,intent(in)  :: iw(2)
  real                :: wsl,wsq,usl,usq,vsl,vsq
  integer             :: n,m
  real,parameter      :: eps=1.0e-30

  ! Standard deviations
  !********************
  wsl=0.
  wsq=0.
  usl=0.
  usq=0.
  vsl=0.
  vsq=0.

  if (interp_state%ngrid.le.0) then ! No nest  
    do m=1,2
      do n=1,2
        call compute_sl_sq(ww,wsl,wsq,iw(n),memind(m),nzmax)
        if (interp_state%ngrid.lt.0) then
          call compute_sl_sq(uupol,usl,usq,iw(n),memind(m),nzmax)
          call compute_sl_sq(vvpol,vsl,vsq,iw(n),memind(m),nzmax)
        else
          call compute_sl_sq(uu,usl,usq,iw(n),memind(m),nzmax)
          call compute_sl_sq(vv,vsl,vsq,iw(n),memind(m),nzmax)
        endif
      end do
    end do
  else ! Nest
    do m=1,2
      do n=1,2
        call compute_sl_sq_nest(wwn,wsl,wsq,iw(n),memind(m),nzmax)
        call compute_sl_sq_nest(uun,usl,usq,iw(n),memind(m),nzmax)
        call compute_sl_sq_nest(vvn,vsl,vsq,iw(n),memind(m),nzmax)
      end do
    end do
  endif

  call stdev(wsl,wsq,16.,interp_state%wsig)
  call stdev(usl,usq,16.,interp_state%usig)
  call stdev(vsl,vsq,16.,interp_state%vsig)

end subroutine stdev_meter
#endif
end module interpol_mod
