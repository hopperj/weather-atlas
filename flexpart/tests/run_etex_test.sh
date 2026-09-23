#!/bin/bash
# By LB
# run ETEX simulations
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
test -d ./default_options
report "[$MM] default options: ./default_options" || exit 1
cp -rf ./default_options ./current
#
# Different options tests
#
STATUS=0
TESTSRUN=0
#
# run Options test with restart output disabled
#
sed -i "/LCONVECTION=/c\ LCONVECTION=      1," ./current/COMMAND
sed -i "/LTURBULENCE=/c\ LTURBULENCE=      1," ./current/COMMAND
#sed -i "/IPOUT=/c\ IPOUT=                  1," ./current/COMMAND
sed -i "/IBDATE=/c\ IBDATE=         19941023," ./current/COMMAND
sed -i "/IBTIME=/c\ IBTIME=           160000," ./current/COMMAND
sed -i "/IEDATE=/c\ IEDATE=         19941027," ./current/COMMAND
sed -i "/IETIME=/c\ IETIME=           110000," ./current/COMMAND
sed -i "/LOUTSTEP=/c\ LOUTSTEP=        10800," ./current/COMMAND
sed -i "/LOUTAVER=/c\ LOUTAVER=        10800," ./current/COMMAND
sed -i "/CTL=/c\ CTL=                10.0000," ./current/COMMAND
sed -i "/IFINE=/c\ IFINE=                  4," ./current/COMMAND
sed -i "/LOUTNETCDFOUT=/c\ LOUTNETCDFOUT=  1," ./current/COMMAND

sed -i "/IDATE1  =/c\ IDATE1  =       19941023," ./current/RELEASES
sed -i "/ITIME1  =/c\ ITIME1  =         160000," ./current/RELEASES
sed -i "/ITIME2  =/c\ ITIME2  =         035000," ./current/RELEASES
sed -i "/IDATE2  =/c\ IDATE2  =       19941024," ./current/RELEASES
sed -i "/LON1    =/c\ LON1    =    -2.00833011," ./current/RELEASES
sed -i "/LON2    =/c\ LON2    =    -2.00833011," ./current/RELEASES
sed -i "/LAT1    =/c\ LAT1    =        48.0583," ./current/RELEASES
sed -i "/LAT2    =/c\ LAT2    =        48.0583," ./current/RELEASES
sed -i "/Z1      =/c\ Z1    =         8.0000," ./current/RELEASES
sed -i "/Z2      =/c\ Z2    =       100.0000," ./current/RELEASES
sed -i "/MASS    =/c\ MASS    =       340.000," ./current/RELEASES
sed -i "/PARTS   =/c\ PARTS   =          10000," ./current/RELEASES

sed -i "/OUTLON0=/c\ OUTLON0=           -10.000," ./current/OUTGRID
sed -i "/OUTLAT0=/c\ OUTLAT0=            43.000," ./current/OUTGRID
sed -i "/NUMXGRID=/c\ NUMXGRID=            101," ./current/OUTGRID
sed -i "/NUMYGRID=/c\ NUMYGRID=             49," ./current/OUTGRID
sed -i "/DXOUT=/c\ DXOUT=              0.5," ./current/OUTGRID
sed -i "/DYOUT=/c\ DYOUT=              0.5," ./current/OUTGRID
sed -i "/OUTHEIGHTS=/c\ OUTHEIGHTS=      100.0" ./current/OUTGRID

cp ./default_etex/RECEPTORS ./current/

cp pathnames pathnames_etex
sed -i "/output/c\./output_etex/" ./pathnames_etex
sed -i "s/default_winds/default_etex/g" ./pathnames_etex
mkdir -p ./output_etex/
./FLEXPART pathnames_etex
report "[$MM] TEST $TESTRUN (ETEX)"
STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))
#
# FINAL
#
echo "[$MM] Tests failed: $STATUS / $TESTSRUN"
#
# Return collective error status
#
exit $STATUS