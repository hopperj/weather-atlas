ARG RL_RELEASE=${RL_RELEASE:-9.1}
FROM quay.io/rockylinux/rockylinux:${RL_RELEASE}-minimal
LABEL maintainer="Flexpart Developers"
COPY <<"EOF" /etc/yum.repos.d/epel-ar.repo
[epel-ar]
name=Extra Packages for Enterprise Linux $releasever - $basearch
baseurl=https://archives.fedoraproject.org/pub/archive/epel/RL_RELEASE/Everything/$basearch/
enabled=1
gpgcheck=0
priority=10
EOF
# this fixes the correct version of the repo, even if just 9 or 8 are used.
# allows to install older version of eccodes and netcdf
RUN export RL_RELEASE=$(cat /etc/redhat-release | awk '{print $4}') && sed -i "s/RL_RELEASE/${RL_RELEASE}/" /etc/yum.repos.d/epel-ar.repo
RUN curl -s --head https://archives.fedoraproject.org/pub/archive/epel/${RL_RELEASE}/Everything/\$basearch/ | grep "200 OK" || (echo "EPEL archive not found for Rocky Linux ${RL_RELEASE}" && rm -fv /etc/yum.repos.d/epel-ar.repo )
RUN export EXTRA_REPO=$((microdnf repolist --all | grep crb 1>/dev/null) && echo crb || echo powertools) && \
	microdnf install -y epel-release && \
	microdnf install -y --enablerepo=${EXTRA_REPO} make netcdf-fortran-devel.x86_64 netcdf.x86_64 eccodes eccodes-devel cmake tar gcc-c++ perl git wget && \
 	microdnf clean all -y && \
 	rm -rf /var/cache/yum
# set environment variables
ENV FC=gfortran
ENV LIBRARY_PATH=/usr/lib64:/usr/local/lib64
ENV CPATH=/usr/include:/usr/local/include:/usr/lib64/gfortran/modules