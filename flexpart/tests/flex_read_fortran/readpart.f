       SUBROUTINE readpart(flexout,datetime,numpart)
       use work_arrays
       implicit none
c      version 2 of 10 columns of reals
c      include '/home/ignacio/flexpart/FLEXPART8.1/includepar'
c      include '/home/ignacio/flexpart/FLEXPART8.1/includecom'
      DOUBLE PRECISION jul
!c      integer itime,i,j,jjjjmmdd,ihmmss itime in work_arrays
      integer i,j,jjjjmmdd,ihmmss
      integer ix,jy,ixp,jyp,indexh,m,il,ind,indz,indzp
      real xlon,ylat
      real dt1,dt2,dtt,ddx,ddy,rddx,rddy,p1,p2,p3,p4,dz1,dz2,dz
      real topo,hm(2),hmixi,pv1(2),pvprof(2),pvi,qv1(2),qvprof(2),qvi
      real tt1(2),ttprof(2),tti,rho1(2),rhoprof(2),rhoi
      real tr(2),tri
      character datetime*14 , flexout*150, filename*150     !atime*6,path*90,directory*90
      integer unitpartout
      integer iargc
      integer npoint
      real ztra1
      integer itramem(1)
c      real topo,pvi,qvi,rhoi,hmixi,tri,tti,
      real xmass(1,1) 
      !integer nspec,p
      integer p
      integer numpart
      integer ios 
      logical verbose

      verbose=.false. ! .true.
      unitpartout=1
      nspec=1

      filename=trim(flexout)//'partposit_'//datetime

      !print*,filename

      if ( datetime(1:1) == '0' ) then
        filename=trim(flexout)
        !print*,filename
        !stop 42
      endif

!      i=0
!      open(unitpartout,file=trim(flexout)//
!c     + 'part2_'//datetime,
!     + 'partposit_'//datetime,
!     + form='unformatted',IOSTAT=ios)
!
      open(unitpartout,file=trim(filename),
     + form='unformatted',IOSTAT=ios)

     
      read(unitpartout) itime
      if ( verbose ) then
        print *, 'readpart2> itime :' , itime
      endif
      if ( numpart==-1 ) then
        do while ( ios == 0 )
!          read(unitpartout, IOSTAT=ios)  xlon,ylat,ztra1,tri,hmixi
          read(unitpartout, IOSTAT=ios)  npoint, xlon,ylat,ztra1, !,tri,hmixi
     +    itramem,topo,pvi,qvi,rhoi,hmixi,tri,tti, xmass

        i=i+1
          if ( verbose ) then
            print *, 'readpart2> i,ios',  i,ios,npoint, xlon,ylat,ztra1 
          endif
!c      print *, 'ios', ios
!c          read(unitpartout) npoint,xlon,ylat,ztra1,
!c     +    itramem(i),topo,pvi,qvi,rhoi,hmixi,tri,tti,
!c     +    (xmass(i,j),j=1,nspec)
!npoint,xlon,ylat,ztra1,
!c     +    itramem(i),topo,pvi,qvi,rhoi,hmixi,tri,tti,
!c     +    xmass
        end do
!          numpart=i-1
          numpart=i-2
      else !numpart~=-1
        do i=1,numpart
!          read(unitpartout, IOSTAT=ios)  xlon,ylat,ztra1,tri,hmixi
!     +    ,topo,pvi,tti,qvi,rhoi
        read(unitpartout, IOSTAT=ios) vnpoint(i), 
     +    vxlon(i),vylat(i), vztra1(i),
     +    vitramem(i),
     +    vtopo(i),vpvi(i),vqvi(i),vrhoi(i),vhmixi(i), 
     +    vtri(i), vtti(i),
     +    (xmass0(i,j),j=1,nspec)
!        print *, 'readpart2> vztra1(i)',vztra1(i) ,i        
!c       vlat(i)=ylat
!c       interpolate OH from the field (needs month, x, y ,z )
!c        OH=
!c          print *, i,   xlon,ylat,ztra1,tri,hmixi
!c     + ,topo,pvi,tti,qvi,rhoi
        end do
      endif ! numpart==-1 
      close(unitpartout)
      end subroutine
