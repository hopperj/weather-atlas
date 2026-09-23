# Trouble Shooting

Here we provide a list of common problems and their solutions. 

<span style="color:seagreen;">
If you have a problem that is not listed or clearly explained by an error message, please create a ticket on our gitlab page by emailing to [gitlab.phaidra+flexpart-flexpart-456-issue-@univie.ac.at](mailto:gitlab.phaidra+flexpart-flexpart-456-issue-@univie.ac.at).
</span>

#### **My application crashes with a segmentation fault shortly after its launch**
This could be due to having compiled with OpenMP, but not setting the following `ulimit` before launching your application, resulting in too little memory per core:
~~~
ulimit -s unlimited
~~~

#### **My application is unexpectedly slow**
There could be many reasons for this to happen, here are some tips to make your application faster:

- Make sure you compiled using appropriate optimisation flags (see [Optimisation](building.md#paths)).
- Check if you need the resolution of output grid, number of particles, and timestep you are currently using and reduce these where possible. For an explanation of all options, see [Configuration](configuration.md).
- Use more OpenMP threads when running your application.
- Make sure to set the following options in your command line (or submit script if you use one) before launching your application:
~~~
export OMP_PLACES=cores
export OMP_PROC_BIND=true
~~~

