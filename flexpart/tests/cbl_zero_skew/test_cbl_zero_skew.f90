program test_cbl_zero_skew
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use cbl_mod, only: reinit_particle
  use com_mod, only: rannumb
  implicit none

  integer :: nrand
  real :: wp

  ! -h/ol=5 is the exact lower-boundary zero of the CBL transition.
  ! This is the condition traced from the frozen one-thread failure.
  nrand=0
  wp=0.25
  rannumb=0.
  rannumb(1)=0.5
  call reinit_particle(0.5, 1.0, 1.0, 1.0, wp, nrand, -0.2)

  if (.not.ieee_is_finite(wp)) then
    error stop "reinit_particle returned a non-finite velocity at zero skew"
  endif
  if (abs(wp-0.5).gt.1.e-6) then
    error stop "zero-skew recovery did not reach the symmetric limit"
  endif
end program test_cbl_zero_skew
