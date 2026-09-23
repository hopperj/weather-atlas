program printpart

use work_arrays

CHARACTER(len=150)     :: flexout
CHARACTER (len=14), dimension(:), ALLOCATABLE  :: dates
CHARACTER (len=14) :: date
integer numpart !,nspec
real :: mx,my,mz



  flexout='/Users/ignacio/repos/flexpart/tests/examples/output_3-part1/'
  !date='20120101080000'
  !date='20120101090000'
  date='20120101100000'
  numpart=-1
  nspec=1

select case (iargc())
case (4)
  call getarg(1,flexout)  
  call getarg(2,date)  
  !call getarg(3,nspec)  
  !call getarg(4,numpart)  
case (3)
  call getarg(1,flexout)  
  call getarg(2,date)  
  !call getarg(3,nspec)  
case (2)
  call getarg(1,flexout)  
  call getarg(2,date)  
case (1)
  call getarg(1,flexout) 
  date='0000'
case (0)
  print*,'0 arguments, default'
  print*, flexout
  print*, date

end select

!CALL readpart2(flexout,dates(idate),numpart)
!CALL readpart2(flexout,date,numpart)
CALL readpart(flexout,date,numpart)

if (.false.) then
print*, 'numpart read:', numpart
numpart=5
endif

ALLOCATE(vnpoint(numpart),vitramem(numpart) )
ALLOCATE(vxlon(numpart),vylat(numpart) ,vztra1(numpart), &
          vtri(numpart),vhmixi(numpart),vtopo(numpart) , &
          vpvi(numpart),vtti(numpart),                   &
          vqvi(numpart),vrhoi(numpart)) 
ALLOCATE(xmass0(numpart,nspec))

CALL readpart(flexout,date,numpart)

if (.false.) then
print*, vnpoint
print*, vxlon
print*, vylat
print*, vztra1
endif

mx = SUM(vxlon)/SIZE(vxlon) 
my = SUM(vylat)/SIZE(vylat) 
mz = SUM(vztra1)/SIZE(vztra1) 

if (.false.) then
print*, 'mean x = ', mx
print*, 'mean y = ', my
print*, 'mean z = ', mz
endif

print*, mx,my,mz


!print*, SUM((vxlon- )**2)/SIZE(Array)

end program
