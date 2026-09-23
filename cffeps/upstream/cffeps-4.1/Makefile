## Makefile for mach_cffeps 
## code uses RPN's rmn and vgrid libraries, make sure appropriate environments are set e.g.:
## for s.compile
## . r.load.dot /fs/ssm/eccc/mrd/rpn/MIG/ENV/rpnpy/2.1-u2.5 main/opt/intelcomp/inteloneapi-2022.1.2/intelcomp+mpi+mkl
## . r.load.dot /fs/ssm/eccc/mrd/rpn/code-tools/1.6.8

SRCDIR=src/mach_cffeps4
LIBS=-lm
INCLUDES=-Iobj
#DEBUG=-g -C -warn all -init=snan -init=arrays

CFLAGS=-traceback
FFLAGS=-O2 -traceback -module ./obj $(INCLUDES)
#CFLAGS=
#FFLAGS=-fbacktrace

BIN=bin/mach_cffeps

OBJS=obj/mach_cffeps_mod.o \
	 obj/mach_readfst.o \
	 obj/mach_cffeps_emissions_mod.o \
	 obj/mach_cffeps_plumes_mod.o \
	 obj/mach_cffeps_fbp_mod.o \
	 obj/mach_cffeps_speciations_mod.o \
	 obj/mach_cffeps_diurnal_mod.o \
	 obj/mach_cffeps.o \
	 obj/mach_cffeps_init.o \
	 obj/mach_cffeps_energy.o \
	 obj/mach_cffeps_procalc.o \
	 obj/mach_cffeps_calc.o

CC=icc
F90=ifort

.PHONY: clean distclean

cffeps4: $(OBJS)
#	$(F90) $(FFLAGS) $(DEBUG) -o $(BIN) $(OBJS) $(LIBS) $(INCLUDES)
	s.compile -optf="$(FFLAGS)" -obj $(OBJS) -o $(BIN) -libappl vgrid rmn

obj/mach_cffeps_mod.mod: $(SRCDIR)/mach_cffeps_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_mod.f90 

obj/mach_readfst.o: $(SRCDIR)/mach_readfst.f90
	s.compile -src $(SRCDIR)/mach_readfst.f90 -compdir obj/ -libappl vgrid rmn -O 2  

obj/mach_cffeps_mod.o: $(SRCDIR)/mach_cffeps_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_mod.f90 -o obj/mach_cffeps_mod.o 

obj/mach_cffeps_emissions_mod.mod: $(SRCDIR)/mach_cffeps_emissions_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_emissions_mod.f90 

obj/mach_cffeps_emissions_mod.o: $(SRCDIR)/mach_cffeps_emissions_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_emissions_mod.f90 -o obj/mach_cffeps_emissions_mod.o  

obj/mach_cffeps_plumes_mod.mod: $(SRCDIR)/mach_cffeps_plumes_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_plumes_mod.f90 

obj/mach_cffeps_plumes_mod.o: $(SRCDIR)/mach_cffeps_plumes_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_plumes_mod.f90 -o obj/mach_cffeps_plumes_mod.o  

obj/mach_cffeps_fbp_mod.mod: $(SRCDIR)/mach_cffeps_fbp_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_fbp_mod.f90 

obj/mach_cffeps_fbp_mod.o: $(SRCDIR)/mach_cffeps_fbp_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_fbp_mod.f90 -o obj/mach_cffeps_fbp_mod.o  

obj/mach_cffeps_speciations_mod.mod: $(SRCDIR)/mach_cffeps_speciations_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_speciations_mod.f90  

obj/mach_cffeps_speciations_mod.o: $(SRCDIR)/mach_cffeps_speciations_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_speciations_mod.f90 -o obj/mach_cffeps_speciations_mod.o 

obj/mach_cffeps_diurnal_mod.o: $(SRCDIR)/mach_cffeps_diurnal_mod.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_diurnal_mod.f90 -o obj/mach_cffeps_diurnal_mod.o 

obj/mach_cffeps.o: $(SRCDIR)/mach_cffeps.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps.f90 -o obj/mach_cffeps.o

obj/mach_cffeps_init.o: $(SRCDIR)/mach_cffeps_init.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_init.f90 -o obj/mach_cffeps_init.o

obj/mach_cffeps_energy.o: $(SRCDIR)/mach_cffeps_energy.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_energy.f90 -o obj/mach_cffeps_energy.o

obj/mach_cffeps_procalc.o: $(SRCDIR)/mach_cffeps_procalc.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_procalc.f90 -o obj/mach_cffeps_procalc.o

obj/mach_cffeps_calc.o: $(SRCDIR)/mach_cffeps_calc.f90
	$(F90) $(FFLAGS) $(DEBUG) -c $(SRCDIR)/mach_cffeps_calc.f90 -o obj/mach_cffeps_calc.o  

$(OBJ_DIR)/%.o: %.f90
	$(F90) $(FFLAGS) -c $@ $<

clean:
	rm -f $(OBJS) obj/*.mod obj/*.f90

distclean: clean
	rm -f $(BIN)
