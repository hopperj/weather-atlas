module random_mod
  implicit none
contains
  real function gasdev(idum,ithread)
    integer, intent(inout) :: idum
    integer, intent(in) :: ithread
    gasdev=0.
  end function gasdev

  real function ran3(idum,ithread)
    integer, intent(inout) :: idum
    integer, intent(in) :: ithread
    ran3=0.5
  end function ran3
end module random_mod
