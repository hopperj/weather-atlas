!arrays changing with time, because of reading or transformation
   MODULE work_arrays
      INTEGER itime
      INTEGER ::  nspec=1
      REAL   , DIMENSION(:,:),ALLOCATABLE :: xmass0(:,:), xmass1(:,:) , xmass1_injected(:,:), xmass1_remaining(:,:)
      REAL   , DIMENSION(:,:),ALLOCATABLE :: xmass1_SG,xmass1_PG
      REAL   , DIMENSION(:,:),ALLOCATABLE :: xmass2 !mass of artificial tracer 
      integer, DIMENSION(:),  ALLOCATABLE :: vnpoint(:),vitramem(:)
      REAL   , DIMENSION(:),  ALLOCATABLE :: vxlon(:),vylat(:),vztra1(:),vtri(:),vhmixi(:),vtopo(:),vpvi(:),vtti(:),vqvi(:),vrhoi(:)
      REAL   , DIMENSION(:),  ALLOCATABLE ::  vxlon2,vxlon3
      INTEGER, DIMENSION(:),  ALLOCATABLE :: i_reach_strat(:), i_reach_400(:), i_reach_2PVU(:)
      INTEGER, DIMENSION(:),  ALLOCATABLE :: reach_strat(:), reach_400(:), reach_2PVU(:), flag_reach_strat(:), flag_over_400(:)
!      INTEGER, DIMENSION(:),  ALLOCATABLE :: ireach_strat(:), ireach_400(:), ireach_2PVU(:)
      INTEGER, DIMENSION(:),  ALLOCATABLE :: secs2_400(:), secs2_380(:), secs2_360(:), secs2_340(:)
      INTEGER, DIMENSION(:),  ALLOCATABLE ::  secs2_conventional(:), secs2_trop_FLEX(:),secs2_2PVU380(:),secs2_35PVU380(:)
      INTEGER ,DIMENSION(:),  allocatable :: ETOW(:),TOW(:),LMS(:),TTL(:),UT(:),STRAT(:),OW(:),MW(:)     
      LOGICAL, DIMENSION(:),  ALLOCATABLE :: l_reached_strat(:),l_reaching_strat(:),l_still_in_trop
      REAL   , DIMENSION(:),  ALLOCATABLE :: vtheta,vpres
      REAL   , DIMENSION(:),  ALLOCATABLE :: lat_in_strat,lat_went_strat
      REAL   , DIMENSION(:,:),ALLOCATABLE :: out_matrix 
      INTEGER, DIMENSION(:,:,:),  ALLOCATABLE :: this_source
      REAL   , DIMENSION(:),  ALLOCATABLE :: lon_down, lat_down
      INTEGER  :: nlon_down, nlat_down
      REAL   , DIMENSION(:,:),ALLOCATABLE ::   chi_30d_strat
      INTEGER, DIMENSION(:,:),  ALLOCATABLE :: N_1, N_0

     ! nspec=1

      
   END MODULE

