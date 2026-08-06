# ZAP Scanning Report

ZAP by [Checkmarx](https://checkmarx.com/).


## Summary of Alerts

| Risk Level | Number of Alerts |
| --- | --- |
| High | 0 |
| Medium | 0 |
| Low | 5 |
| Informational | 9 |




## Insights

| Level | Reason | Site | Description | Statistic |
| --- | --- | --- | --- | --- |
| Low | Warning |  | ZAP warnings logged - see the zap.log file for details | 24    |
| Info | Informational |  | Percentage of network failures | 21 % |
| Info | Informational | http://localhost:3100 | Percentage of responses with status code 2xx | 92 % |
| Info | Informational | http://localhost:3100 | Percentage of responses with status code 4xx | 8 % |
| Info | Informational | http://localhost:3100 | Percentage of endpoints with content type application/javascript | 65 % |
| Info | Informational | http://localhost:3100 | Percentage of endpoints with content type image/svg+xml | 8 % |
| Info | Informational | http://localhost:3100 | Percentage of endpoints with content type text/css | 13 % |
| Info | Informational | http://localhost:3100 | Percentage of endpoints with content type text/html | 13 % |
| Info | Informational | http://localhost:3100 | Percentage of endpoints with method GET | 100 % |
| Info | Informational | http://localhost:3100 | Count of total endpoints | 23    |







## Alerts

| Name | Risk Level | Number of Instances |
| --- | --- | --- |
| Cross-Origin-Embedder-Policy Header Missing or Invalid | Low | 1 |
| Cross-Origin-Opener-Policy Header Missing or Invalid | Low | 1 |
| Cross-Origin-Resource-Policy Header Missing or Invalid | Low | Systemic |
| Permissions Policy Header Not Set | Low | Systemic |
| X-Content-Type-Options Header Missing | Low | Systemic |
| Base64 Disclosure | Informational | 2 |
| Modern Web Application | Informational | 5 |
| Non-Storable Content | Informational | 3 |
| Sec-Fetch-Dest Header is Missing | Informational | 3 |
| Sec-Fetch-Mode Header is Missing | Informational | 3 |
| Sec-Fetch-Site Header is Missing | Informational | 3 |
| Sec-Fetch-User Header is Missing | Informational | 3 |
| Storable and Cacheable Content | Informational | Systemic |
| Storable but Non-Cacheable Content | Informational | 2 |




## Alert Detail



### [ Cross-Origin-Embedder-Policy Header Missing or Invalid ](https://www.zaproxy.org/docs/alerts/90004/)



##### Low (Medium)

### Description

Cross-Origin-Embedder-Policy header is a response header that prevents a document from loading any cross-origin resources that don't explicitly grant the document permission (using CORP or CORS).

* URL: http://localhost:3100
  * Node Name: `http://localhost:3100`
  * Method: `GET`
  * Parameter: `Cross-Origin-Embedder-Policy`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``


Instances: 1

### Solution

Ensure that the application/web server sets the Cross-Origin-Embedder-Policy header appropriately, and that it sets the Cross-Origin-Embedder-Policy header to 'require-corp' for documents.
If possible, ensure that the end user uses a standards-compliant and modern web browser that supports the Cross-Origin-Embedder-Policy header (https://caniuse.com/mdn-http_headers_cross-origin-embedder-policy).

### Reference


* [ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy ](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy)


#### CWE Id: [ 693 ](https://cwe.mitre.org/data/definitions/693.html)


#### WASC Id: 14

#### Source ID: 3

### [ Cross-Origin-Opener-Policy Header Missing or Invalid ](https://www.zaproxy.org/docs/alerts/90004/)



##### Low (Medium)

### Description

Cross-Origin-Opener-Policy header is a response header that allows a site to control if others included documents share the same browsing context. Sharing the same browsing context with untrusted documents might lead to data leak.

* URL: http://localhost:3100
  * Node Name: `http://localhost:3100`
  * Method: `GET`
  * Parameter: `Cross-Origin-Opener-Policy`
  * Attack: ``
  * Evidence: `same-origin-allow-popups`
  * Other Info: ``


Instances: 1

### Solution

Ensure that the application/web server sets the Cross-Origin-Opener-Policy header appropriately, and that it sets the Cross-Origin-Opener-Policy header to 'same-origin' for documents.
'same-origin-allow-popups' is considered as less secured and should be avoided.
If possible, ensure that the end user uses a standards-compliant and modern web browser that supports the Cross-Origin-Opener-Policy header (https://caniuse.com/mdn-http_headers_cross-origin-opener-policy).

### Reference


* [ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy ](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Opener-Policy)


#### CWE Id: [ 693 ](https://cwe.mitre.org/data/definitions/693.html)


#### WASC Id: 14

#### Source ID: 3

### [ Cross-Origin-Resource-Policy Header Missing or Invalid ](https://www.zaproxy.org/docs/alerts/90004/)



##### Low (Medium)

### Description

Cross-Origin-Resource-Policy header is an opt-in header designed to counter side-channels attacks like Spectre. Resource should be specifically set as shareable amongst different origins.

* URL: http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js
  * Node Name: `http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js`
  * Method: `GET`
  * Parameter: `Cross-Origin-Resource-Policy`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/86498b921adc386d.css
  * Node Name: `http://localhost:3100/_next/static/css/86498b921adc386d.css`
  * Method: `GET`
  * Parameter: `Cross-Origin-Resource-Policy`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css
  * Node Name: `http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css`
  * Method: `GET`
  * Parameter: `Cross-Origin-Resource-Policy`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/icon.svg
  * Node Name: `http://localhost:3100/icon.svg`
  * Method: `GET`
  * Parameter: `Cross-Origin-Resource-Policy`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/nycu-favicon.svg
  * Node Name: `http://localhost:3100/nycu-favicon.svg`
  * Method: `GET`
  * Parameter: `Cross-Origin-Resource-Policy`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``

Instances: Systemic


### Solution

Ensure that the application/web server sets the Cross-Origin-Resource-Policy header appropriately, and that it sets the Cross-Origin-Resource-Policy header to 'same-origin' for all web pages.
'same-site' is considered as less secured and should be avoided.
If resources must be shared, set the header to 'cross-origin'.
If possible, ensure that the end user uses a standards-compliant and modern web browser that supports the Cross-Origin-Resource-Policy header (https://caniuse.com/mdn-http_headers_cross-origin-resource-policy).

### Reference


* [ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy ](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cross-Origin-Embedder-Policy)


#### CWE Id: [ 693 ](https://cwe.mitre.org/data/definitions/693.html)


#### WASC Id: 14

#### Source ID: 3

### [ Permissions Policy Header Not Set ](https://www.zaproxy.org/docs/alerts/10063/)



##### Low (Medium)

### Description

Permissions Policy Header is an added layer of security that helps to restrict from unauthorized access or usage of browser/client features by web resources. This policy ensures the user privacy by limiting or specifying the features of the browsers can be used by the web resources. Permissions Policy provides a set of standard HTTP headers that allow website owners to limit which features of browsers can be used by the page such as camera, microphone, location, full screen etc.

* URL: http://localhost:3100/_next/static/chunks/1145-4fbb163c2690db8d.js
  * Node Name: `http://localhost:3100/_next/static/chunks/1145-4fbb163c2690db8d.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/chunks/2954-26bd28d04d34bf73.js
  * Node Name: `http://localhost:3100/_next/static/chunks/2954-26bd28d04d34bf73.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/chunks/app/layout-3dee0c42e78f5d63.js
  * Node Name: `http://localhost:3100/_next/static/chunks/app/layout-3dee0c42e78f5d63.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/chunks/main-app-f3336e172256d2ab.js
  * Node Name: `http://localhost:3100/_next/static/chunks/main-app-f3336e172256d2ab.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js
  * Node Name: `http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: ``
  * Other Info: ``

Instances: Systemic


### Solution

Ensure that your web server, application server, load balancer, etc. is configured to set the Permissions-Policy header.

### Reference


* [ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy ](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy)
* [ https://developer.chrome.com/blog/feature-policy/ ](https://developer.chrome.com/blog/feature-policy/)
* [ https://scotthelme.co.uk/a-new-security-header-feature-policy/ ](https://scotthelme.co.uk/a-new-security-header-feature-policy/)
* [ https://w3c.github.io/webappsec-feature-policy/ ](https://w3c.github.io/webappsec-feature-policy/)
* [ https://www.smashingmagazine.com/2018/12/feature-policy/ ](https://www.smashingmagazine.com/2018/12/feature-policy/)


#### CWE Id: [ 693 ](https://cwe.mitre.org/data/definitions/693.html)


#### WASC Id: 15

#### Source ID: 3

### [ X-Content-Type-Options Header Missing ](https://www.zaproxy.org/docs/alerts/10021/)



##### Low (Medium)

### Description

The Anti-MIME-Sniffing header X-Content-Type-Options was not set to 'nosniff'. This allows older versions of Internet Explorer and Chrome to perform MIME-sniffing on the response body, potentially causing the response body to be interpreted and displayed as a content type other than the declared content type. Current (early 2014) and legacy versions of Firefox will use the declared content type (if one is set), rather than performing MIME-sniffing.

* URL: http://localhost:3100/_next/static/css/551b8e253753964c.css
  * Node Name: `http://localhost:3100/_next/static/css/551b8e253753964c.css`
  * Method: `GET`
  * Parameter: `x-content-type-options`
  * Attack: ``
  * Evidence: ``
  * Other Info: `This issue still applies to error type pages (401, 403, 500, etc.) as those pages are often still affected by injection issues, in which case there is still concern for browsers sniffing pages away from their actual content type.
At "High" threshold this scan rule will not alert on client or server error responses.`
* URL: http://localhost:3100/_next/static/css/86498b921adc386d.css
  * Node Name: `http://localhost:3100/_next/static/css/86498b921adc386d.css`
  * Method: `GET`
  * Parameter: `x-content-type-options`
  * Attack: ``
  * Evidence: ``
  * Other Info: `This issue still applies to error type pages (401, 403, 500, etc.) as those pages are often still affected by injection issues, in which case there is still concern for browsers sniffing pages away from their actual content type.
At "High" threshold this scan rule will not alert on client or server error responses.`
* URL: http://localhost:3100/nycu-favicon.svg
  * Node Name: `http://localhost:3100/nycu-favicon.svg`
  * Method: `GET`
  * Parameter: `x-content-type-options`
  * Attack: ``
  * Evidence: ``
  * Other Info: `This issue still applies to error type pages (401, 403, 500, etc.) as those pages are often still affected by injection issues, in which case there is still concern for browsers sniffing pages away from their actual content type.
At "High" threshold this scan rule will not alert on client or server error responses.`

Instances: Systemic


### Solution

Ensure that the application/web server sets the Content-Type header appropriately, and that it sets the X-Content-Type-Options header to 'nosniff' for all web pages.
If possible, ensure that the end user uses a standards-compliant and modern web browser that does not perform MIME-sniffing at all, or that can be directed by the web application/web server to not perform MIME-sniffing.

### Reference


* [ https://learn.microsoft.com/en-us/previous-versions/windows/internet-explorer/ie-developer/compatibility/gg622941(v=vs.85) ](https://learn.microsoft.com/en-us/previous-versions/windows/internet-explorer/ie-developer/compatibility/gg622941(v=vs.85))
* [ https://owasp.org/www-community/Security_Headers ](https://owasp.org/www-community/Security_Headers)


#### CWE Id: [ 693 ](https://cwe.mitre.org/data/definitions/693.html)


#### WASC Id: 15

#### Source ID: 3

### [ Base64 Disclosure ](https://www.zaproxy.org/docs/alerts/10094/)



##### Informational (Medium)

### Description

Base64 encoded data was disclosed by the application/web server. Note: in the interests of performance not all base64 strings in the response were analyzed individually, the entire response should be looked at by the analyst/security team/developer(s).

* URL: http://localhost:3100/_next/static/chunks/4266-94184e4703d80592.js
  * Node Name: `http://localhost:3100/_next/static/chunks/4266-94184e4703d80592.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/`
  * Other Info: ` �Q� ��0ӏA�QU�a��qן���Y�����ۯ���]�㞻�߿`
* URL: http://localhost:3100/_next/static/chunks/9b0008ae-c5a8f3b980755ba4.js
  * Node Name: `http://localhost:3100/_next/static/chunks/9b0008ae-c5a8f3b980755ba4.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `T1RUTwALAIAAAwAwQ0ZGIDHtZg4AAAOYAAAAgUZGVE1lkzZwAAAEHAAAABxHREVGABQAFQAABDgAAAAeT1MvMlYNYwkAAAEgAAAAYGNtYXABDQLUAAACNAAAAUJoZWFk/xVFDQAAALwAAAA2aGhlYQdkA+oAAAD0AAAAJGhtdHgD6AAAAAAEWAAAAAZtYXhwAAJQAAAAARgAAAAGbmFtZVjmdH4AAAGAAAAAsXBvc3T/hgAzAAADeAAAACAAAQAAAAEAALZRFsRfDzz1AAsD6AAAAADOBOTLAAAAAM4KHDwAAAAAA+gDIQAAAAgAAgAAAAAAAAABAAADIQAAAFoD6AAAAAAD6AABAAAAAAAAAAAAAAAAAAAAAQAAUAAAAgAAAAQD6AH0AAUAAAKKArwAAACMAooCvAAAAeAAMQECAAACAAYJAAAAAAAAAAAAAQAAAAAAAAAAAAAAAFBmRWQAwAAuAC4DIP84AFoDIQAAAAAAAQAAAAAAAAAAACAAIAABAAAADgCuAAEAAAAAAAAAAQAAAAEAAAAAAAEAAQAAAAEAAAAAAAIAAQAAAAEAAAAAAAMAAQAAAAEAAAAAAAQAAQAAAAEAAAAAAAUAAQAAAAEAAAAAAAYAAQAAAAMAAQQJAAAAAgABAAMAAQQJAAEAAgABAAMAAQQJAAIAAgABAAMAAQQJAAMAAgABAAMAAQQJAAQAAgABAAMAAQQJAAUAAgABAAMAAQQJAAYAAgABWABYAAAAAAAAAwAAAAMAAAAcAAEAAAAAADwAAwABAAAAHAAEACAAAAAEAAQAAQAAAC7//wAAAC7////TAAEAAAAAAAABBgAAAQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMAAAAAAAD/gwAyAAAAAQAAAAAAAAAAAAAAAAAAAAABAAQEAAEBAQJYAAEBASH4DwD4GwHEAvgcA/gXBIwMAYuL+nz5tQXkD5j3CBLnEQACAQEBIVhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYAAABAQAADwACAQEEE/t3Dov6fAH6fAT+fPp8+nwHDosMCvm1Cvm1DAz6fBQAAAAAAAABAAAAAMmJbzEAAAAAzgTjFQAAAADOBOQpAAEAAAAAAAAADAAUAAQAAAABAAAAAgABAAAAAAAAAAAD6AAAAAAAAA==`
  * Other Info: `OTTO  �  0CFF 1�f  �   �FFTMe�6p     GDEF    8   OS/2Vc	      `cmap�  4  Bhead�E   �   6hhead�   �   $hmtx�    X   maxp P      nameX�t~  �   �post�� 3  x          �Q�_<� �    ���    �
<    �!             !   Z�    �                  P     ��   ��   ���  � 1   	                     PfEd � . . �8 Z!                      �                                                                  	      	     	     	     	     	     	   X X                  <                .��   .����                                                                                                                                                                                                                                                                                �� 2                     X !� ��������|������ !XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX     �w��|�|�|�|�|�
��
���|          ɉo1    ��    ��)                         �      `


Instances: 2

### Solution

Manually confirm that the Base64 data does not leak sensitive information, and that the data cannot be aggregated/used to exploit other vulnerabilities.

### Reference


* [ https://projects.webappsec.org/w/page/13246936/Information%20Leakage ](https://projects.webappsec.org/w/page/13246936/Information%20Leakage)


#### CWE Id: [ 319 ](https://cwe.mitre.org/data/definitions/319.html)


#### WASC Id: 13

#### Source ID: 3

### [ Modern Web Application ](https://www.zaproxy.org/docs/alerts/10109/)



##### Informational (Medium)

### Description

The application appears to be a modern web application. If you need to explore it automatically then the Client Spider may well be more effective than the standard one.

* URL: http://localhost:3100
  * Node Name: `http://localhost:3100`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `<script src="/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js" async="" nonce="OadQ+I83R/4WeoXQit4MFA=="></script>`
  * Other Info: `No links have been found while there are scripts, which is an indication that this is a modern web application.`
* URL: http://localhost:3100
  * Node Name: `http://localhost:3100`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `<script src="/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js" async="" nonce="Py0eci7vWQ+Olvo/ydgccg=="></script>`
  * Other Info: `No links have been found while there are scripts, which is an indication that this is a modern web application.`
* URL: http://localhost:3100/
  * Node Name: `http://localhost:3100/`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `<script src="/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js" async="" nonce="e5vkQz040CchZ3cy5FUYyA=="></script>`
  * Other Info: `No links have been found while there are scripts, which is an indication that this is a modern web application.`
* URL: http://localhost:3100/robots.txt
  * Node Name: `http://localhost:3100/robots.txt`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `<script src="/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js" async="" nonce="jjsLg8YZEaBv/x+I934dXA=="></script>`
  * Other Info: `No links have been found while there are scripts, which is an indication that this is a modern web application.`
* URL: http://localhost:3100/sitemap.xml
  * Node Name: `http://localhost:3100/sitemap.xml`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `<script src="/_next/static/chunks/4bd1b696-100b9d70ed4e49c1.js" async="" nonce="oePoJHFzQvZMMj1ML55DgA=="></script>`
  * Other Info: `No links have been found while there are scripts, which is an indication that this is a modern web application.`


Instances: 5

### Solution

This is an informational alert and so no changes are required.

### Reference




#### Source ID: 3

### [ Non-Storable Content ](https://www.zaproxy.org/docs/alerts/10049/)



##### Informational (Medium)

### Description

The response contents are not storable by caching components such as proxy servers. If the response does not contain sensitive, personal or user-specific information, it may benefit from being stored and cached, to improve performance.

* URL: http://localhost:3100
  * Node Name: `http://localhost:3100`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `no-store`
  * Other Info: ``
* URL: http://localhost:3100/robots.txt
  * Node Name: `http://localhost:3100/robots.txt`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `no-store`
  * Other Info: ``
* URL: http://localhost:3100/sitemap.xml
  * Node Name: `http://localhost:3100/sitemap.xml`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `no-store`
  * Other Info: ``


Instances: 3

### Solution

The content may be marked as storable by ensuring that the following conditions are satisfied:
The request method must be understood by the cache and defined as being cacheable ("GET", "HEAD", and "POST" are currently defined as cacheable)
The response status code must be understood by the cache (one of the 1XX, 2XX, 3XX, 4XX, or 5XX response classes are generally understood)
The "no-store" cache directive must not appear in the request or response header fields
For caching by "shared" caches such as "proxy" caches, the "private" response directive must not appear in the response
For caching by "shared" caches such as "proxy" caches, the "Authorization" header field must not appear in the request, unless the response explicitly allows it (using one of the "must-revalidate", "public", or "s-maxage" Cache-Control response directives)
In addition to the conditions above, at least one of the following conditions must also be satisfied by the response:
It must contain an "Expires" header field
It must contain a "max-age" response directive
For "shared" caches such as "proxy" caches, it must contain a "s-maxage" response directive
It must contain a "Cache Control Extension" that allows it to be cached
It must have a status code that is defined as cacheable by default (200, 203, 204, 206, 300, 301, 404, 405, 410, 414, 501).

### Reference


* [ https://datatracker.ietf.org/doc/html/rfc7234 ](https://datatracker.ietf.org/doc/html/rfc7234)
* [ https://datatracker.ietf.org/doc/html/rfc7231 ](https://datatracker.ietf.org/doc/html/rfc7231)
* [ https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html ](https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html)


#### CWE Id: [ 524 ](https://cwe.mitre.org/data/definitions/524.html)


#### WASC Id: 13

#### Source ID: 3

### [ Sec-Fetch-Dest Header is Missing ](https://www.zaproxy.org/docs/alerts/90005/)



##### Informational (High)

### Description

Specifies how and where the data would be used. For instance, if the value is audio, then the requested resource must be audio data and not any other type of resource.

* URL: http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js
  * Node Name: `http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Dest`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/86498b921adc386d.css
  * Node Name: `http://localhost:3100/_next/static/css/86498b921adc386d.css`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Dest`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css
  * Node Name: `http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Dest`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``


Instances: 3

### Solution

Ensure that Sec-Fetch-Dest header is included in request headers.

### Reference


* [ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Dest ](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Dest)


#### CWE Id: [ 352 ](https://cwe.mitre.org/data/definitions/352.html)


#### WASC Id: 9

#### Source ID: 3

### [ Sec-Fetch-Mode Header is Missing ](https://www.zaproxy.org/docs/alerts/90005/)



##### Informational (High)

### Description

Allows to differentiate between requests for navigating between HTML pages and requests for loading resources like images, audio etc.

* URL: http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js
  * Node Name: `http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Mode`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/86498b921adc386d.css
  * Node Name: `http://localhost:3100/_next/static/css/86498b921adc386d.css`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Mode`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css
  * Node Name: `http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Mode`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``


Instances: 3

### Solution

Ensure that Sec-Fetch-Mode header is included in request headers.

### Reference


* [ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Mode ](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Mode)


#### CWE Id: [ 352 ](https://cwe.mitre.org/data/definitions/352.html)


#### WASC Id: 9

#### Source ID: 3

### [ Sec-Fetch-Site Header is Missing ](https://www.zaproxy.org/docs/alerts/90005/)



##### Informational (High)

### Description

Specifies the relationship between request initiator's origin and target's origin.

* URL: http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js
  * Node Name: `http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Site`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/86498b921adc386d.css
  * Node Name: `http://localhost:3100/_next/static/css/86498b921adc386d.css`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Site`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css
  * Node Name: `http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css`
  * Method: `GET`
  * Parameter: `Sec-Fetch-Site`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``


Instances: 3

### Solution

Ensure that Sec-Fetch-Site header is included in request headers.

### Reference


* [ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Site ](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-Site)


#### CWE Id: [ 352 ](https://cwe.mitre.org/data/definitions/352.html)


#### WASC Id: 9

#### Source ID: 3

### [ Sec-Fetch-User Header is Missing ](https://www.zaproxy.org/docs/alerts/90005/)



##### Informational (High)

### Description

Specifies if a navigation request was initiated by a user.

* URL: http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js
  * Node Name: `http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js`
  * Method: `GET`
  * Parameter: `Sec-Fetch-User`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/86498b921adc386d.css
  * Node Name: `http://localhost:3100/_next/static/css/86498b921adc386d.css`
  * Method: `GET`
  * Parameter: `Sec-Fetch-User`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css
  * Node Name: `http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css`
  * Method: `GET`
  * Parameter: `Sec-Fetch-User`
  * Attack: ``
  * Evidence: ``
  * Other Info: ``


Instances: 3

### Solution

Ensure that Sec-Fetch-User header is included in user initiated requests.

### Reference


* [ https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-User ](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Sec-Fetch-User)


#### CWE Id: [ 352 ](https://cwe.mitre.org/data/definitions/352.html)


#### WASC Id: 9

#### Source ID: 3

### [ Storable and Cacheable Content ](https://www.zaproxy.org/docs/alerts/10049/)



##### Informational (Medium)

### Description

The response contents are storable by caching components such as proxy servers, and may be retrieved directly from the cache, rather than from the origin server by the caching servers, in response to similar requests from other users. If the response data is sensitive, personal or user-specific, this may result in sensitive information being leaked. In some cases, this may even result in a user gaining complete control of the session of another user, depending on the configuration of the caching components in use in their environment. This is primarily an issue where "shared" caching servers such as "proxy" caches are configured on the local network. This configuration is typically found in corporate or educational environments, for instance.

* URL: http://localhost:3100/_next/static/chunks/2954-26bd28d04d34bf73.js
  * Node Name: `http://localhost:3100/_next/static/chunks/2954-26bd28d04d34bf73.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `max-age=31536000`
  * Other Info: ``
* URL: http://localhost:3100/_next/static/chunks/main-app-f3336e172256d2ab.js
  * Node Name: `http://localhost:3100/_next/static/chunks/main-app-f3336e172256d2ab.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `max-age=31536000`
  * Other Info: ``
* URL: http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js
  * Node Name: `http://localhost:3100/_next/static/chunks/webpack-4419c03630deb7a2.js`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `max-age=31536000`
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/86498b921adc386d.css
  * Node Name: `http://localhost:3100/_next/static/css/86498b921adc386d.css`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `max-age=31536000`
  * Other Info: ``
* URL: http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css
  * Node Name: `http://localhost:3100/_next/static/css/f6de2bba3bf22cdd.css`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `max-age=31536000`
  * Other Info: ``

Instances: Systemic


### Solution

Validate that the response does not contain sensitive, personal or user-specific information. If it does, consider the use of the following HTTP response headers, to limit, or prevent the content being stored and retrieved from the cache by another user:
Cache-Control: no-cache, no-store, must-revalidate, private
Pragma: no-cache
Expires: 0
This configuration directs both HTTP 1.0 and HTTP 1.1 compliant caching servers to not store the response, and to not retrieve the response (without validation) from the cache, in response to a similar request.

### Reference


* [ https://datatracker.ietf.org/doc/html/rfc7234 ](https://datatracker.ietf.org/doc/html/rfc7234)
* [ https://datatracker.ietf.org/doc/html/rfc7231 ](https://datatracker.ietf.org/doc/html/rfc7231)
* [ https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html ](https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html)


#### CWE Id: [ 524 ](https://cwe.mitre.org/data/definitions/524.html)


#### WASC Id: 13

#### Source ID: 3

### [ Storable but Non-Cacheable Content ](https://www.zaproxy.org/docs/alerts/10049/)



##### Informational (Medium)

### Description

The response contents are storable by caching components such as proxy servers, but will not be retrieved directly from the cache, without validating the request upstream, in response to similar requests from other users.

* URL: http://localhost:3100/icon.svg
  * Node Name: `http://localhost:3100/icon.svg`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `max-age=0`
  * Other Info: ``
* URL: http://localhost:3100/nycu-favicon.svg
  * Node Name: `http://localhost:3100/nycu-favicon.svg`
  * Method: `GET`
  * Parameter: ``
  * Attack: ``
  * Evidence: `max-age=0`
  * Other Info: ``


Instances: 2

### Solution



### Reference


* [ https://datatracker.ietf.org/doc/html/rfc7234 ](https://datatracker.ietf.org/doc/html/rfc7234)
* [ https://datatracker.ietf.org/doc/html/rfc7231 ](https://datatracker.ietf.org/doc/html/rfc7231)
* [ https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html ](https://www.w3.org/Protocols/rfc2616/rfc2616-sec13.html)


#### CWE Id: [ 524 ](https://cwe.mitre.org/data/definitions/524.html)


#### WASC Id: 13

#### Source ID: 3


