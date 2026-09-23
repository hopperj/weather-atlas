#!/bin/bash
# By LB
# run ETEX simulations
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
MM='FLEXPART MANUAL NESTS TEST'

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
#
# Different options tests
#
STATUS=0
TESTSRUN=0
# run Options test with nested output
#
sed -i "/LOUTNETCDFOUT=/c\ LOUTNETCDFOUT=  1," ./current/COMMAND

mkdir -p ./output/
./FLEXPART pathnames_nests
report "[$MM] TEST $TESTRUN (NESTS)"

STATUS=$((STATUS + $?))
TESTSRUN=$((TESTSRUN + 1))

./FLEXPART_ETA pathnames_nests
report "[$MM] TEST $TESTRUN (ETA NESTS)"

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