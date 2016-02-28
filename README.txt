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





Design choices on Session model and speaker
	
	To create a session, users need two things: Conference websafekey, and the name of the session
		1. User need to create a Conference first before being able create their own session. Users would need to input the desired Conference's websafeKey, this is to specify what conference will the session be in.
		2. Only required field for a session is name

	Process
	Session model is constructed with the necessary fields to store infromation regarding a session. Session entity can be created through the use of an api endpoint called createSession. Through this endpoint, user can input the session information to be added to datastore. Endpoint then calls another function called createSessionObject. createSessionObject is the main function that creates a session entity in datastore using the information passed through the endpoint.

	The createSession endpoint then returns SessionForm returning all information provided by the user and how it is saved in datastore
	

	User might notice that there are two fields that are not saved in datastore but are part of the createSession endpoint response: websafeConferenceKey and conferenceName. Sessions stored in datastore as children of a specified Conference, this in turn doesn't require Session model to keep additional properties specifically for conference information. Reason why these properties are not part of Session model is because the specified Conference is saved as the parent of a session. It is not needed to be save conference information in the Session model since it can be called using the session key and calling it's parent


	Properties
	Other than specifying the conference's websafekey, the only required field in creating a Session is name. Reason for this is for users to be able to add a sessions even if other session information is not finalized. example, starttime and endtime is not locked yet for any reason.
	-speaker is simply added as string property for simpler implementation
	-starttime and endtime is integer representing (1-24) hours in he day for simpler implementation




Two additional Queries

1. getAllConferences() - this returns all upcoming conferences including present day. This will help users looking for a conference to attend to browse conferences they can still join


2. getSessionsInProgress() - this will return all sessions currently in progress. This is for users currently in the conference to see which sessions they can join at the moment.



Query Problem

Main problem with doing a query excluding a SessionType (which is "workshop") IN a specified cutoff time (which is after 7pm). Main problem with this is forcing the developer to use two inequality filters in one query.

To solve this problem, an inequality filter is applied to SessionType, and then on all the sessions on the query, a for loop is used to scan the sessions' [starttime] one by one. This will allow the developer to use a python if statement to act as another inequality filter outside the Datastore's limitation of only able to use one inequality filter on one query

getSessionPreference() - is implemented as a solution to this query problem. It asks for what SessionType to exclude in the query, and then asks for the user's time availability. The user's availability is then used to use a python if statement for every session remaining in the query.
