#!/bin/bash
# By MB
# run default tests
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
MM='FLEXPART AUTOMATIC OPTIONS TEST'

warning() {
    printf "%-68s[$YELLOW%10s$NC]\n" "$@" "SKIPPED"
    return 0
}

report() {
    if [ $? -eq 0 ]; then
        printf "%-68s[$GREEN%10s$NC]\n" "$@" "OK"
        return 0
    else
        printf "%-68s[$RED%10s$NC]\n" "$@" "FAILED"
        return 1
    fi
}
#
# initial conditions
#
warning "[$MM] $PWD"
#
# Change to directory of this script
#
cd $(dirname $0)
#
# Check for Flexpart executable build before
#
test -f ../src/FLEXPART
report "[$MM] executable: ../src/FLEXPART" || exit 1
ln -s ../src/FLEXPART .
ln -s ../src/FLEXPART_ETA .
test -d ./default_options
report "[$MM] default options: ./default_options" || exit 1
cp -rf ./default_options ./current
mkdir -p ./output/
#
# Different options tests
#
STATUS=0
TESTSRUN=0
#
#
# 
#BACKWARD WET DEPOSITION
cp -rf ./default_options ./current
sed -i "/LDIRECT=/c\ LDIRECT=   -1," ./current/COMMAND
# change release
# 
# IND_RECEPTOR=          1, ! Unit to be used at the receptor; [0]no receptor [1]mass 2]mass mixing ratio 3]wet depo. 4]dry depo.
# ! Release start time in UTC HHMISS: HH hours, MI=minutes, SS=seconds
sed "/SPECNUM_REL=/c\ SPECNUM_REL=   40," ./default_options/RELEASES > ./current/RELEASES
sed -i "/PSHAPE=/c\ PSHAPE= 0," ./current/SPECIES/SPECIES_040
sed -i "/PDQUER=/c\ PDQUER=1.0E-06," ./current/SPECIES/SPECIES_040
sed -i "/ITIME1  =/c\ ITIME1  =   030000," ./current/RELEASES
sed -i "/ITIME2  =/c\ ITIME2  =   030000," ./current/RELEASES
sed -i "/LON1    =/c\ LON1    =    -50.0," ./current/RELEASES
sed -i "/LON2    =/c\ LON2    =    50.0," ./current/RELEASES
sed -i "/LAT1    =/c\ LAT1    =        10.0," ./current/RELEASES
sed -i "/LAT2    =/c\ LAT2    =        80.0," ./current/RELEASES
sed -i "/Z1      =/c\ Z1      =         1.0000," ./current/RELEASES
sed -i "/Z2      =/c\ Z2      =       100.0000," ./current/RELEASES
sed -i "/IND_RECEPTOR/c\ IND_RECEPTOR=  3," ./current/COMMAND
sed -i "/IOUTPUTFOREACHRELEASE=/c\ IOUTPUTFOREACHRELEASE=  1," ./current/COMMAND

cp pathnames pathnames_tmp
sed -i "/output/c\./output_bkw/" ./pathnames_tmp
mkdir output_bkw

./FLEXPART pathnames_tmp

cp pathnames pathnames_tmp
sed -i "/output/c\./output_bkw_eta/" ./pathnames_tmp
mkdir output_bkw_eta

./FLEXPART_ETA pathnames_tmp

report "[$MM] TEST $TESTRUN (IND_RECEPTOR=3)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current
#
# 
#BACKWARD DRY DEPOSITION
cp -rf ./default_options ./current
sed -i "/LDIRECT=/c\ LDIRECT=   -1," ./current/COMMAND
sed "/SPECNUM_REL=/c\ SPECNUM_REL=   40," ./default_options/RELEASES > ./current/RELEASES
sed -i "/PSHAPE=/c\ PSHAPE= 0," ./current/SPECIES/SPECIES_040
sed -i "/PDQUER=/c\ PDQUER=1.0E-06," ./current/SPECIES/SPECIES_040
sed -i "/ITIME1  =/c\ ITIME1  =   030000," ./current/RELEASES
sed -i "/ITIME2  =/c\ ITIME2  =   030000," ./current/RELEASES
sed -i "/LON1    =/c\ LON1    =    -50.0," ./current/RELEASES
sed -i "/LON2    =/c\ LON2    =    50.0," ./current/RELEASES
sed -i "/LAT1    =/c\ LAT1    =        10.0," ./current/RELEASES
sed -i "/LAT2    =/c\ LAT2    =        80.0," ./current/RELEASES
sed -i "/Z1      =/c\ Z1    =         1.0000," ./current/RELEASES
sed -i "/Z2      =/c\ Z2    =       100.0000," ./current/RELEASES
sed -i "/IND_RECEPTOR/c\ IND_RECEPTOR=  4," ./current/COMMAND
sed -i "/IOUTPUTFOREACHRELEASE=/c\ IOUTPUTFOREACHRELEASE=  1," ./current/COMMAND

cp pathnames pathnames_tmp
sed -i "/output/c\./output_bkw/" ./pathnames_tmp
./FLEXPART pathnames_tmp

cp pathnames pathnames_tmp
sed -i "/output/c\./output_bkw_eta/" ./pathnames_tmp
./FLEXPART_ETA pathnames_tmp

report "[$MM] TEST $TESTRUN (IND_RECEPTOR=4)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current
#
#
#Convection
cp -rf ./default_options ./current
sed -i "/LCONVECTION=/c\ LCONVECTION=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (LCONVECTION=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#Turbulence
cp -rf ./default_options ./current
sed -i "/LTURBULENCE=/c\ LTURBULENCE=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (LTURBULENCE=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#Mesoscale turbulence
cp -rf ./default_options ./current
sed -i "/LTURBULENCE_MESO=/c\ LTURBULENCE_MESO=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (LTURBULENCE_MESO=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#CTL option
cp -rf ./default_options ./current
sed -i "/LTURBULENCE=/c\ LTURBULENCE=  1," ./current/COMMAND
sed -i "/CTL=/c\ CTL=  10.0000," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (CTL=10)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#CBLFLAG
cp -rf ./default_options ./current
sed -i "/LTURBULENCE=/c\ LTURBULENCE=  1," ./current/COMMAND
sed -i "/CTL=/c\ CTL=  10.0000," ./current/COMMAND
sed -i "/IFINE=/c\ IFINE=  10," ./current/COMMAND
sed -i "/CBLFLAG=/c\ CBLFLAG=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (CBLFLAG=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#NETCDF output
cp -rf ./default_options ./current
sed -i "/IOUT=/c\ IOUT=  9," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (IOUT=9)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#NETCDF particle output
cp -rf ./default_options ./current
sed -i "/IPOUT=/c\ IPOUT=  1," ./current/COMMAND
sed "/SPECNUM_REL=/c\ SPECNUM_REL=   40," ./default_options/RELEASES > ./current/RELEASES
sed -i "/PSHAPE=/c\ PSHAPE= 0," ./current/SPECIES/SPECIES_040
sed -i "/LON1    =/c\ LON1    =    10.00833011," ./current/RELEASES
sed -i "/LON2    =/c\ LON2    =    30.00833011," ./current/RELEASES
sed -i "/LAT1    =/c\ LAT1    =        20.0583," ./current/RELEASES
sed -i "/LAT2    =/c\ LAT2    =        50.0583," ./current/RELEASES
sed -i "/Z1      =/c\ Z1      =         0.0100," ./current/RELEASES
sed -i "/Z2      =/c\ Z2      =       100.0100," ./current/RELEASES
sed -i "/PDQUER/c\ PDQUER=1.0E-06" ./current/SPECIES/SPECIES_040

cp pathnames pathnames_tmp
sed -i "/output/c\./output_settling/" ./pathnames_tmp
#sed -i "s/default_winds/default_etex/g" ./pathnames_tmp
mkdir output_settling
export OMP_NUM_THREADS=1
./FLEXPART pathnames_tmp

cp pathnames pathnames_tmp
sed -i "/output/c\./output_settling_eta/" ./pathnames_tmp
#sed -i "s/default_winds/default_etex/g" ./pathnames_tmp
mkdir output_settling_eta
./FLEXPART_ETA pathnames_tmp

export OMP_NUM_THREADS=32
report "[$MM] TEST $TESTRUN (IPOUT=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current
#
#
#NETCDF particle output at the end
cp -rf ./default_options ./current
sed -i "/IPOUT=/c\ IPOUT=  2," ./current/COMMAND
sed "/SPECNUM_REL=/c\ SPECNUM_REL=   40," ./default_options/RELEASES > ./current/RELEASES
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (IPOUT=2)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#LSUBGRID
cp -rf ./default_options ./current
sed -i "/LSUBGRID=/c\ LSUBGRID=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (LSUBGRID=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#AGESPECTRA
cp -rf ./default_options ./current
sed -i "/LAGESPECTRA=/c\ LAGESPECTRA=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (LAGESPECTRA=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#
#OUTRESTART
cp -rf ./default_options ./current
sed -i "/LOUTRESTART=/c\ LOUTRESTART=  3600," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (LOUTRESTART=3600)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
#
# and IPIN
mv output/restart_20090101020000 output/restart.bin
sed -i "/IPIN=/c\ IPIN=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (IPIN=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#PART_IC.NC input
cp -rf ./default_options ./current
sed -i "/IPIN=/c\ IPIN=  3," ./current/COMMAND
sed -i "/LDIRECT=/c\ LDIRECT=   -1," ./current/COMMAND
sed -i "/LOUTRESTART=/c\ LOUTRESTART=  3600," ./current/COMMAND
sed -i "/IOUTPUTFOREACHRELEASE=/c\ IOUTPUTFOREACHRELEASE=  1," ./current/COMMAND
sed -i "/IOUT=/c\ IOUT=  1," ./current/COMMAND
sed -i "/IBTIME=/c\ IBTIME=  020000," ./current/COMMAND
sed -i "/LOUTSTEP=/c\ LOUTSTEP=  3600," ./current/COMMAND
sed -i "/LOUTAVER=/c\ LOUTAVER=  3600," ./current/COMMAND
cp -rf part_ic.nc current/
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (IPIN=3)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))

# and IPIN=4
mv output/restart_20090101020000 output/restart.bin
sed -i "/IPIN=/c\ IPIN=  4," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (IPIN=4)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#IFLUX
cp -rf ./default_options ./current
sed -i "/IFLUX=/c\ IFLUX=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (IFLUX=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#MDOMAINFILL
cp -rf ./default_options ./current
sed -i "/MDOMAINFILL=/c\ MDOMAINFILL=  1," ./current/COMMAND
sed -i "/NXSHIFT=/c\ NXSHIFT=   89," ./current/COMMAND
sed -i "/IOUT=/c\ IOUT=   0," ./current/COMMAND
sed -i "/IPOUT=/c\ IPOUT=   1," ./current/COMMAND
sed -i "/LOUTNETCDFOUT=/c\ LOUTNETCDFOUT=   1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (MDOMAINFILL=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#MQUASILAG
cp -rf ./default_options ./current
sed -i "/MQUASILAG=/c\ MQUASILAG=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (MQUASILAG=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#NESTED_OUTPUT
cp -rf ./default_options ./current
sed -i "/NESTED_OUTPUT=/c\ NESTED_OUTPUT=  1," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (NESTED_OUTPUT=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#NESTED_INPUT
#
#
#LINIT_COND
cp -rf ./default_options ./current
sed -i "/LINIT_COND=/c\ LINIT_COND=  1," ./current/COMMAND
sed -i "/LNETCDFOUT=/c\ LNETCDFOUT=  0," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (LINIT_COND=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#SFC_ONLY
cp -rf ./default_options ./current
sed -i "/SFC_ONLY=/c\ SFC_ONLY=  1," ./current/COMMAND
sed -i "/LNETCDFOUT=/c\ LNETCDFOUT=  0," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (SFC_ONLY=1)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*
#
#
#MAXTHREADGRID
cp -rf ./default_options ./current
sed -i "/MAXTHREADGRID=/c\ MAXTHREADGRID=  10," ./current/COMMAND
./FLEXPART pathnames
report "[$MM] TEST $TESTRUN (MAXTHREADGRID=10)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
# clean up
rm -rf ./current ./output/*

# Test particale output (ipout=1)
# between openmp=1 and openmp=?? the locations should be identical
# no convection no turbulence
#

#
# Add comaprison with MASTER branch outputs
# add as a volume
#
#

#
# FINAL
#
echo "[$MM] Tests failed: $STATUS / $TESTSRUN"
#
# Return collective error status
#
exit $STATUS
