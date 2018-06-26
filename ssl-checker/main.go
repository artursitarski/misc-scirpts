/*
 * This simple application checks how many days left
 * to the expiration date. It compares SSL cert "Expires On"
 * with current time and rounds the difference up to days.
 * *accuracy +/- 1 day
 */

package main

import (
	"crypto/tls"
	"crypto/x509"
	"flag"
	"fmt"
	"os"
	"regexp"
	"strings"
	"time"
)

func main() {
	siteName := flag.String("site", "", "Site name to check")
	flag.Parse()

	if *siteName == "" {
		fmt.Println("You have to provide site URL to check.")
		os.Exit(1)
	}

	sslCert := getCertificate(*siteName)
	daysLeft := getDaysLeft(sslCert.NotAfter)

	fmt.Println(daysLeft)
}

func getCertificate(host string) *x509.Certificate {
	conn, err := getSSLConnetion(host)

	if err != nil {
		fmt.Printf("Something went wrong with TLS connection: %s", err)
		os.Exit(1)
	}

	var sslCert *x509.Certificate

	for _, c := range conn.ConnectionState().PeerCertificates {
		// Replace * in wildcard cert with valid regexp to compare to
		certCN := strings.Replace(c.Subject.CommonName, "*.", "^[a-z0-9-]*.?", 1)
		regexpCN := regexp.MustCompile(certCN)

		if regexpCN.MatchString(host) {
			sslCert = c
			break
		}
	}

	if sslCert == nil {
		fmt.Printf("%s does not contain proper SSL certificate.", host)
		os.Exit(1)
	}

	return sslCert
}

func getSSLConnetion(hostURL string) (*tls.Conn, error) {
	conf := &tls.Config{
		InsecureSkipVerify: true,
	}

	return tls.Dial("tcp", hostURL+":443", conf)
}

func getDaysLeft(validityDate time.Time) int {
	now := time.Now()
	hoursLeft := validityDate.Sub(now).Hours()

	return int(hoursLeft / 24)
}
