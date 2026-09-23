#!/bin/bash
# display in 83 columns
source ./declare_examples

i=$1


examples_value=$(echo "examples"$i)
#echo $examples_value
     #printf -v "examplesi" "%s" "$examples_value" 
     #echo $examplesi
examples="${examples_value}[@]"
#echo examples 1: $examples
    #export examples=("${examplesi[@]}") 
export examples=("${!examples}")
   #echo ${examples[@]}
   #echo examples 2: $examples[@] 
#echo examples 2: ${examples[@] }
echo examples: ${examples[@] }

array_name=$(echo "units"$i)
units="${array_name}[@]"
export units=("${!units}")
echo units: ${units[@] }
  
#export formats=("${formati[@]}") 

array_name=$(echo "format"$i)
target_array="${array_name}[@]"
export formats=("${!target_array}")
echo formats: ${formats[@] }

array_name=$(echo "filens"$i)
target_array="${array_name}[@]"
export filens=("${!target_array}")
echo filens : ${filens[@] }

#source ./display_examples.sh
# output eg:
#3-1_part 20120101100000 part
#3-2_part_end end part
#3-3_part_bwd 20120101080000 part
