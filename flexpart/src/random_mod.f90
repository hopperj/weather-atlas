! SPDX-FileCopyrightText: FLEXPART 1998-2019, see flexpart_license.txt
! SPDX-License-Identifier: GPL-3.0-or-later

!  Taken from Press et al., Numerical Recipes

module random_mod
  
  implicit none

  integer, parameter :: ran1_ntab=32
  type :: random_thread_state
    integer :: ran1_iv(ran1_ntab)
    integer :: ran1_iy
    integer :: gasdev_iset
    real :: gasdev_gset
    integer :: ran3_iff
    integer :: ran3_inext,ran3_inextp
    integer :: ma(55)
    integer :: iseed1,iseed2
    ! The active fields occupy 380 bytes with four-byte default integers/reals.
    ! A 132-byte guard makes the 512-byte stride larger than two Apple Silicon
    ! cache lines, preventing adjacent threads from sharing a line regardless
    ! of the allocator's base alignment.
    integer :: cache_guard(33)
  end type random_thread_state

  type(random_thread_state), allocatable :: random_state(:)

contains
  
  subroutine alloc_random(num_threads)

    implicit none

    integer :: num_threads, i,stat,env_status,seed_length
    integer(kind=8) :: configured_seed
    character(len=32) :: seed_text
    logical :: has_configured_seed

    has_configured_seed=.false.
    configured_seed=0_8
    seed_text=''
    call get_environment_variable('FLEXPART_RANDOM_SEED',seed_text, &
      length=seed_length,status=env_status)
    if (env_status.eq.0 .and. seed_length.gt.0) then
      read(seed_text(1:seed_length),*,iostat=env_status) configured_seed
      if (env_status.ne.0 .or. configured_seed.lt.1_8 .or. &
          configured_seed.gt.2147483647_8) then
        error stop 'FLEXPART_RANDOM_SEED must be an integer from 1 to 2147483647'
      endif
      has_configured_seed=.true.
    endif

    allocate(random_state(0:num_threads-1),stat=stat)
    if (stat.ne.0) error stop "Could not allocate random thread states"

    do i=0,num_threads-1
      if (has_configured_seed) then
        random_state(i)%iseed1=-1-int(mod(configured_seed-1_8+104729_8*i, &
          2147483000_8))
        random_state(i)%iseed2=-1-int(mod(configured_seed-1_8+1000003_8+13007_8*i, &
          2147483000_8))
      else
        random_state(i)%iseed1=-7-i
        random_state(i)%iseed2=-88-i
      endif
      random_state(i)%ran3_iff=0
      random_state(i)%ran1_iv=0
      random_state(i)%ran1_iy=0
      random_state(i)%gasdev_iset=0
      random_state(i)%gasdev_gset=0.
      random_state(i)%cache_guard=0
    end do
  end subroutine alloc_random

  subroutine dealloc_random()

    deallocate(random_state)
  end subroutine dealloc_random

  function ran1(idum,ithread)

    implicit none

    integer :: idum,ithread
    real    :: ran1
    integer,parameter :: ia=16807, im=2147483647, iq=127773, ir=2836
    integer,parameter :: ndiv=1+(im-1)/ran1_ntab
    real,parameter    :: am=1./im, eps=1.2e-7, rnmx=1.-eps
    integer :: j, k

    if (idum.le.0.or.random_state(ithread)%ran1_iy.eq.0) then
      idum=max(-idum,1)
      do j=ran1_ntab+8,1,-1
        k=idum/iq
        idum=ia*(idum-k*iq)-ir*k
        if (idum.lt.0) idum=idum+im
        if (j.le.ran1_ntab) random_state(ithread)%ran1_iv(j)=idum
      enddo
      random_state(ithread)%ran1_iy=random_state(ithread)%ran1_iv(1)
    endif
    k=idum/iq
    idum=ia*(idum-k*iq)-ir*k
    if (idum.lt.0) idum=idum+im
    j=1+random_state(ithread)%ran1_iy/ndiv
    random_state(ithread)%ran1_iy=random_state(ithread)%ran1_iv(j)
    random_state(ithread)%ran1_iv(j)=idum
    ran1=min(am*random_state(ithread)%ran1_iy,rnmx)
  end function ran1


  function gasdev(idum,ithread)

    implicit none

    integer :: idum,ithread
    real    :: gasdev, fac, r, v1, v2

    if (random_state(ithread)%gasdev_iset.eq.0) then
1     v1=2.*ran3(idum,ithread)-1.
      v2=2.*ran3(idum,ithread)-1.
      r=v1**2+v2**2
      if(r.ge.1.0 .or. r.eq.0.0) go to 1
      fac=sqrt(-2.*log(r)/r)
      random_state(ithread)%gasdev_gset=v1*fac
      gasdev=v2*fac
      random_state(ithread)%gasdev_iset=1
    else
      gasdev=random_state(ithread)%gasdev_gset
      random_state(ithread)%gasdev_iset=0
    endif
  end function gasdev


  subroutine gasdev1(idum,random1,random2)

    implicit none

    integer :: idum
    real :: random1, random2, fac, v1, v2, r

1   v1=2.*ran3(idum,0)-1.
    v2=2.*ran3(idum,0)-1.
    r=v1**2+v2**2
    if(r.ge.1.0 .or. r.eq.0.0) go to 1
    fac=sqrt(-2.*log(r)/r)
    random1=v1*fac
    random2=v2*fac
! Limit the random numbers to lie within the interval -3 and +3
!**************************************************************
    if (random1.lt.-3.) random1=-3.
    if (random2.lt.-3.) random2=-3.
    if (random1.gt.3.) random1=3.
    if (random2.gt.3.) random2=3.
  end subroutine gasdev1


  function ran3(idum,ithread)

    implicit none

    integer :: idum,ithread
    real :: ran3

    integer,parameter :: mbig=1000000000, mseed=161803398, mz=0
    real,parameter    :: fac=1./mbig
    integer :: i,ii,k
    integer :: mj,mk

    if(idum.lt.0 .or. random_state(ithread)%ran3_iff.eq.0)then
      random_state(ithread)%ran3_iff=1
      mj=mseed-iabs(idum)
      mj=mod(mj,mbig)
      random_state(ithread)%ma(55)=mj
      mk=1
      do i=1,54
        ii=mod(21*i,55)
        random_state(ithread)%ma(ii)=mk
        mk=mj-mk
        if(mk.lt.mz)mk=mk+mbig
        mj=random_state(ithread)%ma(ii)
      end do
      do k=1,4
        do i=1,55
          random_state(ithread)%ma(i)=random_state(ithread)%ma(i)- &
            random_state(ithread)%ma(1+mod(i+30,55))
          if(random_state(ithread)%ma(i).lt.mz) &
            random_state(ithread)%ma(i)=random_state(ithread)%ma(i)+mbig
        end do
      end do
      random_state(ithread)%ran3_inext=0
      random_state(ithread)%ran3_inextp=31
      idum=1
    endif
    random_state(ithread)%ran3_inext=random_state(ithread)%ran3_inext+1
    if(random_state(ithread)%ran3_inext.eq.56) &
      random_state(ithread)%ran3_inext=1
    random_state(ithread)%ran3_inextp=random_state(ithread)%ran3_inextp+1
    if(random_state(ithread)%ran3_inextp.eq.56) &
      random_state(ithread)%ran3_inextp=1
    mj=random_state(ithread)%ma(random_state(ithread)%ran3_inext)- &
      random_state(ithread)%ma(random_state(ithread)%ran3_inextp)
    if(mj.lt.mz)mj=mj+mbig
    random_state(ithread)%ma(random_state(ithread)%ran3_inext)=mj
    ran3=mj*fac
  end function ran3
!  (C) Copr. 1986-92 Numerical Recipes Software US.

end module random_mod
