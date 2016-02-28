#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'


from datetime import datetime
from datetime import date

import endpoints
from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb
from google.appengine.api import memcache

from models import StringMessage
from models import ConflictException
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import BooleanMessage
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForm
from models import ConferenceQueryForms
from models import TeeShirtSize
from models import Session
from models import SessionForm
from models import SessionForms

from utils import getUserId

from settings import WEB_CLIENT_ID

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
MEMCACHE_FEATURED_SPEAKER = "FEATURED_SPEAKER"

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": ["Default", "Topic"],
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

FIELDS =    {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
            }

CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

# for creating session
SESS_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1),
)

# for getConferenceSessions
SESS_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeKey=messages.StringField(1),
)


SESS_GET_REQUEST_TYPE = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    typeOfSession=messages.StringField(2)
)

SESS_GET_REQUEST_SPEAKER = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker=messages.StringField(1),
)

SESS_POST_REQUEST_SESSIONKEY = endpoints.ResourceContainer(
    message_types.VoidMessage,
    sessionKey=messages.StringField(1)
)

SESS_GET_REQUEST_PREFERENCE = endpoints.ResourceContainer(
    message_types.VoidMessage,
    excludeSessionType=messages.StringField(1),
    availabilityStart=messages.IntegerField(2),
    availabilityEnd=messages.IntegerField(3),
)
# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


@endpoints.api(name='conference', version='v1',
    allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID],
    scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Conference objects - - - - - - - - - - - - - - - - -

    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf

    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        print '$$$$$$$$$$$$$$$$$$$$$$$ printing of date[startDate]', data['startDate']
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            print '$$$$$$$$$$$$$$$$$$$$$$$ printing of date[startDate] AFTER', data['startDate']
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            print '$$$$$$$$$$$$$$$$$$$$$$$ printing of date[endDate]', data['endDate']
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()
            print '$$$$$$$$$$$$$$$$$$$$$$$ printing of date[endDate]', data['endDate']

        # set seatsAvailable to be same as maxAttendees on creation
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        # TODO 2: add confirmation email sending task to queue
        taskqueue.add(
            params={'email': user.email(),
            'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
            )

        return request

    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {
            field.name: getattr(
                request,
                field.name
                ) for field in request.all_fields()
            }

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(
        ConferenceForm,
        ConferenceForm,
        path='conference',
        http_method='POST',
        name='createConference'
        )
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(
        CONF_POST_REQUEST,
        ConferenceForm,
        path='conference/{websafeConferenceKey}',
        http_method='PUT', name='updateConference'
        )
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)

    @endpoints.method(
        CONF_GET_REQUEST,
        ConferenceForm,
        path='conference/{websafeConferenceKey}',
        http_method='GET', name='getConference'
        )
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))

    @endpoints.method(
        message_types.VoidMessage,
        ConferenceForms,
        path='getConferencesCreated',
        http_method='POST',
        name='getConferencesCreated'
        )
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)
        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, getattr(prof, 'displayName')) for conf in confs]
        )

    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q

    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {
                field.name: getattr(
                    f,
                    field.name
                    ) for field in f.all_fields()
                }

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException(
                    "Filter contains invalid field or operator."
                    )

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException(
                        "Inequality filter is allowed on only one field."
                        )
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

    @endpoints.method(
        ConferenceQueryForms,
        ConferenceForms,
        path='queryConferences',
        http_method='POST',
        name='queryConferences'
        )
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
                items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in \
                conferences]
        )

# - - - Profile objects - - - - - - - - - - - - - - - - - - -

    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf

    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key=p_key,
                displayName=user.nickname(),
                mainEmail=user.email(),
                teeShirtSize=str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile

    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
            prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)

    @endpoints.method(
        message_types.VoidMessage,
        ProfileForm,
        path='profile',
        http_method='GET', name='getProfile'
        )
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()

    @endpoints.method(
        ProfileMiniForm,
        ProfileForm,
        path='profile',
        http_method='POST',
        name='saveProfile'
        )
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)


# - - - Registration - - - - - - - - - - - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser()  # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)

    @endpoints.method(
        message_types.VoidMessage,
        ConferenceForms,
        path='conferences/attending',
        http_method='GET',
        name='getConferencesToAttend'
        )
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser()  # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])\
         for conf in conferences]
        )

    @endpoints.method(
        CONF_GET_REQUEST,
        BooleanMessage,
        path='conference/{websafeConferenceKey}',
        http_method='POST', name='registerForConference'
        )
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)

    @endpoints.method(
        CONF_GET_REQUEST,
        BooleanMessage,
        path='conference/{websafeConferenceKey}',
        http_method='DELETE', name='unregisterFromConference'
        )
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)


# - - - Announcements - - - - - - - - - - - - - - - - - - - -

    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = '%s %s' % (
                'Last chance to attend! The following conferences '
                'are nearly sold out:',
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)

        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(
        message_types.VoidMessage,
        StringMessage,
        path='conference/announcement/get',
        http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        # TODO 1
        # return an existing announcement from Memcache or an empty string.
        announcement = memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY)
        if not announcement:
            announcement = ""
        return StringMessage(data=announcement)


# - - - Sessions - - - - - - - - - - - - - - - - - - - - - - -
    
    def _copySessionToForm(self, sess_post_request):
        """Copy relevant fields from SESS_POST_REQUEST to SessionForm."""
        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess_post_request, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('date'):
                    setattr(sf, field.name, str(getattr(sess_post_request, field.name)))
                # copy remaining fields
                else:
                    setattr(sf, field.name,
                            getattr(sess_post_request, field.name)
                            )
        # add conference name and key to form using session's websafeKey by getting parent
        sess = ndb.Key(urlsafe=sess_post_request.websafeKey)
        conf = sess.parent().get()
        conf_urlsafe = sess.parent().urlsafe()
        setattr(sf, 'websafeConferenceKey', conf_urlsafe)
        setattr(sf, 'conferenceName', conf.name)
        sf.check_initialized()
        return sf

    def createSessionObject(self, request):
        """Create or update Session object, returning SessionForm/request."""
        # check if user is logged in
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # get conference object using websafeConferenceKey
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey
                )

        # check that user is owner of conference
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # convert date string to date object
        date_convert = request.date
        if date_convert:
            date_convert = datetime.strptime(date_convert[:10], "%Y-%m-%d").date()
        # saving variables in the request to Session()
        sess = Session()
        sess.name = request.name
        sess.highlights = request.highlights
        sess.speaker = request.speaker
        sess.duration = request.duration
        sess.typeOfSession = request.typeOfSession
        sess.date = date_convert
        #sess.websafeConferenceKey = request.websafeConferenceKey
        #sess.conferenceName = conf.name
        sess.startTime = request.startTime
        sess.endTime = request.endTime

        # getting sessionkey with conference as parent
        c_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        s_id = Session.allocate_ids(size=1, parent=c_key)[0]
        s_key = ndb.Key(Session, s_id, parent=c_key)
        sess.key = s_key
        sess.websafeKey = s_key.urlsafe()
        sess.put()

        # calling cacheFeaturedSpeaker using taskqueue
        taskqueue.add(
            params={
                'speaker': request.speaker,
                'websafeConferenceKey': request.websafeConferenceKey
                },
            url='/tasks/set_featured_speaker'
            )
        return self._copySessionToForm(sess)

    @endpoints.method(
        SESS_POST_REQUEST,
        SessionForm,
        path='conference/{websafeConferenceKey}/session',
        http_method='POST', name='createSession'
        )
    def createSession(self, request):
        """Create new Session."""
        return self.createSessionObject(request)

    @endpoints.method(
        CONF_GET_REQUEST,
        SessionForms,
        path='conference/session-list/{websafeConferenceKey}',
        http_method='GET', name='getConferenceSessions'
        )
    def getConferenceSessions(self, request):
        """Return all sessions in the given websafeConferenceKey"""
        conf_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        sessions = Session.query(ancestor=conf_key)
        print '######################################################'
        print '######################################################'
        print sessions
        return SessionForms(
            items=[
                self._copySessionToForm(session) for session in sessions
                ]
            )

    @endpoints.method(
        SESS_GET_REQUEST_TYPE,
        SessionForms,
        path='conference/session-list-type/{websafeConferenceKey}/{typeOfSession}',
        http_method='GET', name='getConferenceSessionsByType'
        )
    def getConferenceSessionsByType(self, request):
        """Return all sessions in the given websafeConferenceKey"""
        conf_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        sessions = Session.query(ancestor=conf_key)
        sessions = sessions.filter(Session.typeOfSession == request.typeOfSession)

        return SessionForms(items=[self._copySessionToForm(session) for session in sessions])

    @endpoints.method(
        SESS_GET_REQUEST_SPEAKER,
        SessionForms,
        path='conference/session-list-speaker/{speaker}',
        http_method='GET', name='getSessionsBySpeaker'
        )
    def getSessionsBySpeaker(self, request):
        """Return all session by given speaker"""
        sessions = Session.query()
        sessions = sessions.filter(Session.speaker == request.speaker)

        return SessionForms(
                items=[
                self._copySessionToForm(session) for session in sessions
                   ]
               )

    def _getSessionByKey(self, sessionKey):
        session = ndb.Key(urlsafe=sessionKey)
        if not session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % sessionKey)
        #check if key provided is a session
        if session.kind() != 'Session':
            raise endpoints.BadRequestException("Key provided is not a Session kind")
        return session

    @endpoints.method(
        SESS_POST_REQUEST_SESSIONKEY,
        ProfileForm,
        path='conference/session-add-wishlist/{sessionKey}',
        http_method='POST', name='addSessionToWishlist'
        )
    def addSessionToWishlist(self, request):
        """Add Session in user wishlist"""
        self._getSessionByKey(request.sessionKey)
        profile = self._getProfileFromUser()
        profile.sessionKeyToAttend.append(request.sessionKey)
        profile.put()

        return self._copyProfileToForm(profile)

    @endpoints.method(
        SESS_POST_REQUEST_SESSIONKEY,
        ProfileForm,
        path='conference/session-delete-wishlist/{sessionKey}',
        http_method='POST', name='deleteSessionInWishlist'
        )
    def deleteSessionInWishlist(self, request):
        """Delete Session in user wishlist"""
        self._getSessionByKey(request.sessionKey)
        profile = self._getProfileFromUser()
        if request.sessionKey in profile.sessionKeyToAttend:
            profile.sessionKeyToAttend.pop(profile.sessionKeyToAttend.index(request.sessionKey))
        profile.put()
        return self._copyProfileToForm(profile)

    @endpoints.method(
        message_types.VoidMessage,
        SessionForms,
        path='getSessionsInWishlist',
        http_method='GET',
        name='conference/session-wishlist'
        )
    def getSessionsInWishlist(self, request):
        """get all sessions in wishlist"""
        prof = self._getProfileFromUser()
        sess_keys_to_attend = [ndb.Key(urlsafe=key) for key in prof.sessionKeyToAttend]
        sessions = ndb.get_multi(sess_keys_to_attend)
        return SessionForms(
            items=[
                self._copySessionToForm(session) for session in sessions
                ]
            )

    @endpoints.method(
        SESS_GET_REQUEST,
        SessionForm,
        path='conference/session/{websafeKey}',
        http_method='GET', name='getSession'
        )
    def getSession(self, request):
        """get information for specific session"""
        sess = self._getSessionByKey(request.websafeKey).get()
        return self._copySessionToForm(sess)


    @endpoints.method(
        message_types.VoidMessage,
        ConferenceForms,
        path='conference/allconferences',
        http_method='GET', name='getAllConferences'
        )
    def getAllConferences(self, request):
        """get today and all upcoming conferences"""       
        
        # query all present and upcoming conferences
        confs = Conference.query()
        confs = confs.filter(Conference.startDate>=date.today())

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in confs]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])\
         for conf in confs]
        )


    @endpoints.method(
        CONF_GET_REQUEST,
        SessionForms,
        path='conference/sessions-in-progress',
        http_method='GET', name='getSessionsInProgress'
        )
    def getSessionsInProgress(self, request):
        """get current sessions in progress of specified conference"""
        hour_now = datetime.now().time().hour
        conf_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        sessions = Session.query(ancestor=conf_key)
        sess_filtered = []
        for session in sessions:
            if session.startTime <= hour_now:
                if session.endTime >= hour_now:
                    sess_filtered.append(session)
                    
        return SessionForms(
            items=[
                self._copySessionToForm(session) for session in sessions
                ]
            )

    @endpoints.method(
        SESS_GET_REQUEST_PREFERENCE,
        SessionForms,
        path='conference/session/preference/{excludeSessionType}/{availabilityStart}/{availabilityEnd}',
        http_method='GET', name='getSessionPreference'
        )
    def getSessionPreference(self, request):
        """get list of sessions that
        meets excludeSessionType and availability"""
        # this is to solve the problem
        # of needing two inequality filters
        sess_filtered = []
        sessions = Session.query()
        sessions = sessions.filter(
            Session.typeOfSession != request.excludeSessionType
            )
        for session in sessions:
            # checks against user's hour of availability from 1-24 hours,
            # against the hour the session starts
            if session.startTime >= request.availabilityStart:
                if session.endTime <= request.availabilityEnd:
                    sess_filtered.append(session)

        return SessionForms(
            items=[
                self._copySessionToForm(session) for session in sess_filtered
                ]
            )

    @staticmethod
    def setFeaturedSpeaker(speaker, websafeConferenceKey):
        """check if speaker has multiple sessions,
        if yes, return speaker's sessions"""
        print '$$$$$$$$$$$$$$$ start of setFeaturedSpeaker'
        conf_key = ndb.Key(urlsafe=websafeConferenceKey)
        sessions = Session.query(ancestor=conf_key)
        sessions = sessions.filter(Session.speaker == speaker)

        # check if speaker has multiple sessions
        count = 0
        for session in sessions:
            count += 1
        if count > 1:
            sess_list = ', '.join(session.name for session in sessions)
            message = ('%s %s' % (
                'Come and join %s ' % speaker,
                'on the following sessions:(%s)' % sess_list))
            # if true, add to memcache
            print '$$$$$$$$$$$$$$ ADDING TO MEMCACHE'
            memcache.set(MEMCACHE_FEATURED_SPEAKER, message)


    @endpoints.method(
        message_types.VoidMessage,
        StringMessage,
        path='conference/featured-speaker/get',
        http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Return Featured Speaker from memcache."""
        featured_speaker = memcache.get(MEMCACHE_FEATURED_SPEAKER)
        if not featured_speaker:
            featured_speaker = ""
        return StringMessage(data=featured_speaker)

api = endpoints.api_server([ConferenceApi])  # register API


