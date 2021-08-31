# officer-pdf
soffice container / REST API, facilitates conversion of office documents to pdf.

## Usage

```bash
$ docker run -ti -p 8080:8080 btimby/officer-pdf
$ curl --output test.pdf \
       --header "Content-Type: application/vnd.oasis.opendocument.text" \
       --data-binary @"test.odt" http://localhost:8008/pdf/?pages=1-1

$ # OR - send a URL:
$ curl --output test.pdf http://localhost:8008/pdf/?url=https://google.com/

$ # OR - send a path:
$ curl --output test.pdf http://localhost:8008/pdf/?url=file:///documents/foo.odt

$ # OR the same as above with png output:
$ curl --output test.png http://localhost:8008/png/?url=https:/google.com/

$ # To perform a health check:
$ curl http://localhost:8000/
```

## What is it?

This is a dead simple REST interface for soffice headless mode. The motivation
for this is that I wanted to use the soffice uno bridge within node and this
allowed me to do so easily.

## Docker / environment options

`MAX_CONCURRENCY=1` This environment variable controls how many conversions
happen concurrently. One is important for the stability of the soffice
headless server. The HTTP server can accept multiple concurrent requests but
conversions are serialized via a queue.

`MAX_MEMORY=10485760` The maximum file size to be stored in memory. Disk is used
for input files exceeding this limit. The corresponding output file is also written
to disk.

`MAX_CHUNK=16384` The chunk sized used when copying buffers.

`TEMP_DIR=<system default>` The directory used for large input and output files.

## REST Interface

### Parameters

 - `pages` Querystring argument that must be in the form of `'1-2'`
two numbers separated by a dash (`-`). You can provide a `Content-Type` header
to help soffice determine the file type. Otherwise, the POST body must be the
file to be converted (with no encoding).
 - `headers` When using an HTTP URL these headers will be sent with the request.
 - `cookies` Whne using an HTTP URL these cookies will be sent with the request.

HTTP `Transfer-Encoding: chunked` is supported or the usual `Content-Length`
header must be present.

The return value will have `Content-Type: application/pdf` and will be a PDF
file containing the requested pages.

## Notes

The soffice process is started as soon as the program starts. A background
thread monitors the process health and restarts it if necessary.

The HTTP `Content-Type` header is used to determine the input file type when
POSTing a file. For GET requests, when a local file URL is passed, the extension
is used to determine the type. For remote URLs, a HEAD request is performed
to retrieve the file size and content type.

The health check converts a trivial block of text to a PDF and reports a 200
if it succeeds and a 503 if not.

When using local file URLs, be sure to map in any files you want to be
accessible.

```bash
$ docker run -ti -v /path/to/files:/path/to/files:ro -p 8008:8008 btimby/officer-pdf

$ curl --output test.pdf http://localhost:8008/pdf/?url=file:///path/to/files/myfile.docx
```