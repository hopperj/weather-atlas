default:
	./set_default_example.sh
examples: default
	./gen_options_all.sh
	./gen_pathnames.sh	
batch: examples 
	./gen_batch_jobs_cl.sh
run: batch
	./run_batch_cl.sh
clean:
	rm -r options* pathnames* output* *.cl *.cl.stdout

clean_:
	rm -r options_* pathnames_* output_* *.cl *.cl.stdout

run_:
	./gen_pathnames.sh
	./gen_batch_jobs_cl.sh
	./run_batch_cl.sh

cleanrun:
	rm *.out rm *.err *.sl
cleandefault: 
	rm -r options pathnames output
