# soffice-rest
soffice container / REST API.

## Usage

```bash
$ docker run -ti -p 8080:8080 btimby/soffice-rest
$ curl --output test.pdf --data-binary @"test.odt" http://localhost:8008/?pages=1-1
```

## What is it?

This is a dead simple REST interface for soffice headless mode. The motivation
for this is that I wanted to use the soffice uno bridge within node and this
allowed me to do so easily.

## Docker / environment options

`MAX_CONCURRENCY=1` This environment variable controls how many conversions
happen concurrently. One is important for the stability of the soffice
headless server.

While the HTTP server is based on `aiohttp` and can handle many concurrent
clients, requests are queued and converted one at a time.

## REST Interface

You can pass a `pages` querystring argument that must be in the form of `'1-2'`
two numbers separated by a dash (`-`). You can provide a `Content-Type` header
to help soffice determine the file type. Otherwise, the POST body must be the
file to be converted (with no encoding).

HTTP `Transfer-Encoding: chunked` is supported or the usual `Content-Length`
header must be present.

The return value will have `Content-Type: application/pdf` and will be a PDF
file containing the requested pages.

## Notes

The soffice process is started as soon as the program starts. A background
thread monitors the process health and restarts it if necessary.
