README


This program functions as the backend API for Conference Central app.

How to run:
1. install Python 2.7 
	download link here: https://www.python.org/downloads/release/python-2710/

2. install google app engine SDK for python
	download link here: https://cloud.google.com/appengine/downloads#Google_App_Engine_SDK_for_Python

3. unzip conference-central.zip to a folder

4. using google app engine launcher, add the conference-central to app engine
	a. open google app engine launcher
	b. go to File->Add Existing Application
	c. click browse and select the conference-central folder 
	d. click add
	
5. conference central should now be in google app engine

6 select conference central and then hit the deploy button

7. access the conference-central API by using a webbrowser and going to the address below
	https://conference-central-1145.appspot.com/_ah/api/explorer





Design choices on Session and Speaker

Session model properties below explaining design decisions:
	-conferencekey property is added on the createSessionObject function using the request
	-Speaker field is NOT required to help creator setup a place holder if speaker is not finalized
	-speaker is simply added as string property for simpler implementation
	-starttime and endtime is integer representing (1-24) hours in the day for simpler implementation



Two additional Queries

1. getSession() - this will return all sessions currently registered in the conference. This will enable users to browse available sessions to see specific topics even though they haven't regiestered to a specific conference

2. getSessionsInWishlist() - this will return all sessions added by user to their own wishlist. This will let users see what have they added to their wishlist



Query Problem

Main problem with searching doing a query excluding a SessionType (which is "workshop") IN a specified cutoff time (which is after 7pm). Main problem with this is forcing the developer the use two inequality filters to one query.

To solve this problem, an inequality filter is applied to SessionType, and then on all the sessions on the query, a for loop is used to scan the sessions' [starttime] one by one. This will allow the developer to use a python if statement to act as another inequality filter outside the Datastore's limitation of only able to use one inequality filter on one query

getSessionPreference() - is implemented as a solution to this query problem. It asks for what SessionType to exclude in the query, and then asks for the user's time availability. The user's availability is then used to use a python if statement for every session remaining in the query.
