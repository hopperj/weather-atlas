SHELL = /bin/bash

FC       = gfortran

INCPATH2 = /opt/tools/netcdf-fortran/4.6.0-gcc9.4/include 
LIBPATH2 = /opt/tools/netcdf-fortran/4.6.0-gcc9.4/lib 
 
 
FFLAGS   = -I$(INCPATH2) 
 
LIBS = -lnetcdff 
 
LDFLAGS  = $(FFLAGS) -L$(LIBPATH2) -Wl,-rpath,$(LIBPATH2) $(LIBS)  


print:  printgrid_ncf printgrid printpart

all: flex_read_compare2 printheader printgrid printpart

%.o: %.f90
	+$(FC) -c $(FFLAGS) $<		
#	+$(FC) -c $<		
flex_read_compare2:readheader.o readgrid.o juldate.o caldate.o flex_read_compare2.o 
	$(FC) readheader.o readgrid.o juldate.o caldate.o flex_read_compare2.o -o flex_read_compare2
printheader:readheader1090.o juldate.o caldate.o readheader_stdout90.o 
	$(FC) readheader1090.o juldate.o caldate.o readheader_stdout90.o -o printheader
printgrid:readheader.o readgrid.o juldate.o caldate.o printgrid.o 
	$(FC) readheader.o readgrid.o juldate.o caldate.o printgrid.o -o printgrid
printpart:work_arrays.o readpart.o printpart.o
#	$(FC) -c work_arrays.f90 readpart.f printpart.f90 
	$(FC) work_arrays.o readpart.o printpart.o -o printpart

#printgrid_ncf:readheader.o readheader_ncf.o readgrid.o juldate.o caldate.o printgrid_ncf.o 
#	$(FC) readheader.o readheader_ncf.o readgrid.o juldate.o caldate.o printgrid_ncf.o -o printgrid_ncf $(LDFLAGS)
printgrid_ncf: readheader_ncf.o readgrid_ncf.o juldate.o caldate.o printgrid_ncf.o 
	$(FC)  readheader_ncf.o readgrid_ncf.o juldate.o caldate.o printgrid_ncf.o -o printgrid_ncf $(LDFLAGS)
clean:
	        rm *.o
		rm *.mod
reset: 
	rm  *.o *.mod printpart printgrid printgrid_ncf printheader flex_read_compare2

output=../../output/
test: 
	./printheader $(output)
	./printgrid $(output) conc
