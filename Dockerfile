FROM continuumio/miniconda3

WORKDIR "/app"
ADD . /app

RUN apt-get install -y build-essential nmap

RUN conda create -n env python=3.7
RUN ["/bin/bash", "-c", ". /opt/conda/etc/profile.d/conda.sh && \
    conda activate env && \
    pip install -e ."]

RUN echo "source activate env" > ~/.bashrc
ENV PATH /opt/conda/envs/env/bin:$PATH

ENTRYPOINT ["homie-hue-bridge"]

EXPOSE 8005 
EXPOSE 1900
