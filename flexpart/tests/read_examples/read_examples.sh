#!/bin/bash

# export printgrid=$HOME/repos/flexpart/postproc/flex_read_fortran/printgrid

# default path to examples
#examples_default=./
#examples_default=../../examples
examples_default=../examples
# environment override on default
#examples_int=${1:-$examples_default}
examples_env=${examples:-$examples_default}
#internal (argument override)
examples_int=${1:-$examples_env}


#printgrid_default=printgrid
#printgrid_default=/Users/ignacio/repos/flexpart/postproc/flex_read_fortran/printgrid
printgrid_default=../flex_read_fortran/printgrid
# todo test exixtence of executable
# alternative: printgrid_default=$HOME/repos/flexpart/postprocess/read_fortran/printgrid
#overrun by input from ENV
printgrid_env=${printgrid:-$printgrid_default}
# overrun by command line arguments 
printgrid_int=${2:-$printgrid_env}

#printpart_default=../../postprocess/flex_read_fortran_part/printpart
printpart_default=../flex_read_fortran/printpart
#overrun by input from ENV
printpart_env=${printpart:-$printpart_default}
# overrun by command line arguments 
printpart_int=${2:-$printpart_env}



echo default example
stdout=$($printgrid_int $examples_int/output/ conc)
echo default $stdout

set_examples_default=set_examples_1.sh
echo default example variations $set_examples_default

set_examples_env=${set_examples:-$set_examples_default} 

#source ./set_examples_3.sh
#source ./set_examples_1.sh
#source ./set_examples_all
source ./${set_examples_env}

echo 'echo ${examples[@]}' 
echo ${examples[@]} 

iend=$(( ${#examples[@]} - 1 ))
#echo $(( iend + 1 )) 
echo loop on $(( iend + 1  )) examples  
ii=0
for i in `seq 0 $iend`;
do 
  ii=$(( ii + 1 ))
  #echo $i
  #echo $example
  b=${example:0:1}
  #echo $b
#  if [ $i == 3 ]; then  ii=3 ; fi
  if [ $i == 3 ] && [ $b == 1 ]; then  ii=3 ; fi

  example=${examples[$i]}
  unit=${units[$i]}
  format=${formats[$i]}
#    if [ $unit == "x" ]; then
#      echo $i '&' "not gridded binary"
#    else
    if [ $format == "cm" ]; then
      #echo $printgrid_int $examples_int/output_${example}/ ${unit}
      #stdout=$($printgrid_int $examples_int/output_1-1/ conc)
      stdout=$($printgrid_int $examples_int/output_${example}/ ${unit})
      #echo $i '&' ${example}: $stdout
      echo $ii '&' ${example} '&' $stdout '\\'
    elif [ $format == "part" ]; then
      #echo $printpart_int $examples_int/output_${example}/ ${unit}
      stdout=$($printpart_int $examples_int/output_${example}/ ${unit})
      echo $ii '&' ${example} '& xyz:' $stdout '\\'     
    elif [ $format == "nc" ]; then
      grid_conc_default="grid_conc_20190225190000.nc"
      grid_conc_env=${grid_conc:-$grid_conc_default} 
      #echo ${printgrid_int}_ncf $examples_int/output_${example}/ ${unit} $grid_conc_env
      filen=${filens[$i]}
      #echo $filen
      stdout=$(${printgrid_int}_ncf $examples_int/output_${example}/ ${unit} $filen)
      #stdout=$(${printgrid_int}_ncf $examples_int/output_${example}/ ${unit} $grid_conc_env)
      #echo $stdout
      echo $ii '&' ${example} '&' $stdout '\\'       
    else
      echo $ii '&' ${example} '&' $format "not yet supported"
    fi
done

exit
$printgrid_int $examples_int/output_2/ pptv

$printgrid_int $examples_int/output_bwd/ time


exit 
