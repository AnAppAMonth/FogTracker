# FogTracker

[FogTracker][] is a Free and Open Source Software web application and a free service
to integrate [FogBugz][] and [Pivotal Tracker][]. It's written in Python and for
[Google AppEngine][].

## Key Features

*	Two-way integration. A user can import a FogBugz case into Pivotal Tracker via
	Drag & Drop, or import a new or existing Pivotal Tracker story into FogBugz by
	assigning a special label to it. After the initial import, the FogBugz case and
	the Pivotal Tracker story are linked to each other, and any further change or
	comment on either side will be propagated to or reported in the other side.

*	You can link multiple FogBugz projects to one Pivotal Tracker project, multiple
	Pivotal Tracker projects to one FogBugz project, or multiple FogBugz projects to
	multiple Pivotal Tracker projects. However, each FogBugz case can only be linked
	with a single Pivotal Tracker story, and vice versa.

*	FogTracker works with both FogBugz On Demand and your private FogBugz server.

## More Information

You can find more information on FogTracker and even try it out on its website: <br/>
<https://fogtracker.appspot.com/>

Have a suggestion? Want to discuss? Leave a comment here: <br/>
<http://www.ban90.com/2011/01/24/fogbugz-pivotal-tracker-fogtracker/#comment>

The interfacing with FogBugz is based on [pyfogbugz][], a Python wrapper of the
FogBugz API also hosted on GitHub.

[FogTracker]: https://fogtracker.appspot.com/
[FogBugz]: http://www.fogcreek.com/FogBugz/
[Pivotal Tracker]: https://www.pivotaltracker.com
[Google AppEngine]: http://code.google.com/appengine/
[pyfogbugz]: https://github.com/paltman/pyfogbugz
