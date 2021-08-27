FROM debian:bullseye

ENV DEBIAN_FRONTEND noninteractive
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

RUN apt-get update && \
    apt-get -y install \
    ure libreoffice libreoffice-core libreoffice-java-common libreoffice-common \
    libreoffice-writer libreoffice-impress libreoffice-calc libreoffice-draw \
    openjdk-17-jre fonts-opensymbol hyphen-fr hyphen-de hyphen-en-us \
    hyphen-it hyphen-ru fonts-dejavu fonts-dejavu-core fonts-dejavu-extra \
    fonts-droid-fallback fonts-dustin fonts-f500 fonts-fanwood \
    fonts-freefont-ttf fonts-liberation fonts-lmodern fonts-lyx \
    fonts-sil-gentium fonts-texgyre fonts-tlwg-purisa python3-pip \
    python3-uno pipenv && \
    apt-get -y upgrade && \
    apt-get -y autoremove && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

ADD rest/ /app/
WORKDIR /app
RUN pipenv install --system

ENTRYPOINT ["python3", "/app/"]
