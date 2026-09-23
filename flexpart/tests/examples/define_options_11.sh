suffix=_11-1_Volc
options_new=options$suffix
cp -r  $options_template $options_new
sed -i '/IOUT=/c\ IOUT=1,' $options_new/COMMAND
cp RELEASES_Grimsvotn_FPrun3_2012 $options_new/RELEASES
