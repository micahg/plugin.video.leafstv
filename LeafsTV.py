'''
@author: Micah Galizia <micahgalizia@gmail.com>
'''

import urllib, urllib2, re, time

class LeafsTVError(Exception):
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)


class LeafsTV:
    
    """
    Class to handle LeafsTV Interactive web requests
    """
    
    def __init__(self, username, password):
        """
        Initialize the class
        """
        
        self.username = username
        self.password = password
        return
    

    def authenticate(self):
        """
        Authenticate with Leafs TV Interactive
        """
        
        # set up the username and password
        values = {'username' : self.username,
                  'password' : self.password }
        
        
        # set up the request and add the post data (user and pass)
        req = urllib2.Request("https://leafstv.neulion.com/leafstv/secure/login")
        req.add_data(urllib.urlencode(values))
        
        # make the request and read the response
        try:
            resp = urllib2.urlopen(req)
        except:
            return False
        
        if resp.read().find("<code>loginsuccess</code>") < 0:
            return False
        
        self.cookie = resp.headers.get("Set-Cookie")
        
        return True;

    
    def getGames(self):
        """
        Get the list of games available on LeafsTV Interactive
        """
        
        # create teh request
        req = urllib2.Request("http://leafstv.neulion.com/leafstv/servlets/games")
        req.add_header('cookie', self.cookie)
        
        # make the request and read the response
        try:
            resp = urllib2.urlopen(req)
        except urllib2.URLError, ue:
            raise LeafsTVError("URL error trying to open games list: " + ue.read())
        except urllib2.HTTPError, he:
            raise LeafsTVError("HTTP error trying to open games list: " + he.read())
        
        return self.parseGamesList(resp.read())
    
    
    def parseGamesList(self, list):
        """
        parse the string containing the list of games
        """

        # first cut out only the list
        start = list.find("[") + 1
        end = list.find("]")
        real_list = list[start:end]
        offset = 0
        games = []
        
        # loop through each game in the list
        while offset < len(real_list):
            
            # search for the next '}' that encapsulates the game
            game_end = real_list[offset:len(real_list)].find("}") + 1 + offset
            
            # get just the game
            game = self.parseGame(real_list[offset:game_end])
            
            if game == None:
                continue
            
            games.append(game)
            
            #move the offset past the '}' and the game delimiting ','
            offset += (game_end - offset) + 1

        return games


    def parseGame(self, game):
        """
        parse a single game string. This method returns a dictionary containing
        information about a single game.
        """
        
        # get the start of the long date
        date_start = game.find("\"longStartDate\"") + 17
        date_end = game[date_start:len(game)].find("\"") + date_start
        
        # try to parse date/time formated as '01/13/2012 19:30:00'
        try:
            game_time = time.strptime(game[date_start:date_end], "%m/%d/%Y %H:%M:%S")
        except ValueError, ve:
            print "Unable to parse time for game '" + game + "'"
            return None

        # parse the home team        
        home_start = game.find("\"homeTeamName\"") + 16
        home_end = game[home_start:len(game)].find("\"") + home_start
        home_team = game[home_start:home_end]

        # parse the away team
        away_start = game.find("\"awayTeamName\"") + 16
        away_end = game[away_start:len(game)].find("\"") + away_start
        away_team = game[away_start:away_end]

        # parse the id
        id_start = game.find("\"id\"") + 5
        id_end = game[id_start:len(game)].find(",") + id_start
        id = game[id_start:id_end]
        
        game_dict = {'time' : game_time, 'home_team' : home_team,
                     'away_team' : away_team,'id' : id }
        
        # parse the start time. If it contains a value this game has not
        # happened yet, so we can just ignore it later on
        start_start = game.find("\"startTime\"") + 13
        start_end = game[start_start:len(game)].find("\"")
        if start_end > 0:
            game_dict['start_time'] = game[start_start:start_start + start_end]
            
        # parse the progressTime. I'm assuming this is our clue to which game
        # is live. Games not in progress do not have this field and ended games
        # have "progressTime":"FINAL". Live games will have a value of
        # "progressTime":"LIVE"
        progress_start = game.find("\"progressTime\"")
        if progress_start >= 0:
            progress_start += 16
            progress_end = game[progress_start:len(game)].find("\"") + progress_start
            progress = game[progress_start:progress_end]
            game_dict['progress'] = progress
        else:
            game_dict['progress'] = ""
        
        return game_dict


    def prioritizeGames(self, games):
        """
        Put the games in priority watching order. Right now this just puts the
        a live game first.
        """
        
        # loop over each game and if the progress is live, add it to the start
        for game in games:
            if game['progress'] == "LIVE":
                games.remove(game)
                games.insert(0, game)
                break;
        
        return games


    def getLiveGame(self):
        """
        Get a live game
        """
        
        # set the post data
        values = {'isFlex' : "true"}
        
        # create the request
        req = urllib2.Request("http://leafstv.neulion.com/leafstv/servlets/game")
        req.add_header('cookie', self.cookie)
        req.add_data(urllib.urlencode(values))
        
        # make the request and read the response
        try:
            resp = urllib2.urlopen(req)
        except urllib2.URLError, ue:
            raise LeafsTVError("URL error trying to open game: " + ue.read())
        except urllib2.HTTPError, he:
            raise LeafsTVError("HTTP error trying to open game: " + he.read())

        # try to pull the program id
        match = re.search('<programId>(.*?)</programId>', resp.read())
        if match == None:
            raise LeafsTVError("Unable to find programId")

        # ensure a valid program id exists
        try:
            program_id = match.group(1)
        except IndexError:
            raise LeafsTVError("Invalid program ID")
        
        # by default use the 1600 bitrate... poor, I know, but that is the best
        full_id = program_id + "_1600"
        try:
            live_game = self.getEncryptedLiveGame(full_id)
        except LeafsTVError, ltvError:
            raise ltvError
        
        return live_game


    def getEncryptedLiveGame(self, path):
        
        values = {'isFlex' : "true",
                   'type' : "game",
                   'path' : path }
        
        req = urllib2.Request("http://leafstv.neulion.com/leafstv/servlets/encryptvideopath")
        req.add_header('cookie', self.cookie)
        req.add_data(urllib.urlencode(values))
        
        # make the request and read the response
        try:
            resp = urllib2.urlopen(req)
        except urllib2.URLError, ue:
            raise LeafsTVError("URL error trying to open game: " + ue.read())
        except urllib2.HTTPError, he:
            raise LeafsTVError("HTTP error trying to open game: " + he.read())
        
        match = re.search('<path><\!\[CDATA\[(.*?)\]\]></path>', resp.read())
        if match == None:
            raise LeafsTVError("Unable to match live game with <path/>")

        try:
            url = match.group(1)
        except IndexError, ie:
            raise LeafsTVError("ERROR: Unable to get URL from live game")

        return url


    def getArchivedGame(self, game_id, type=2):
        """
        Get an archived game.
        """
        
        # get the id of the archived game
        #id = game['id']
        id = game_id[len(game_id)-4:len(game_id)]
        
        # setup the POST values
        values= {'isFlex' : "true",
                 'type' : str(type),
                 'id' : id }
        
        # setup the request
        req = urllib2.Request("http://leafstv.neulion.com/leafstv/servlets/archive")
        req.add_header('cookie', self.cookie)
        req.add_data(urllib.urlencode(values))
        
        try:
            resp = urllib2.urlopen(req)
        except urllib2.URLError, ue:
            raise LeafsTVError("URL error trying to open archive: " + ue.read())
        except urllib2.HTTPError, he:
            raise LeafsTVError("HTTP error trying to open archive: " + he.read())
        
        match = re.search('<publishPoint><\!\[CDATA\[(.*?)\]\]></publishPoint>', resp.read())
        if match == None:
            
            # we have recursed down to preseason and that also did not work             
            if type == 1:
                raise LeafsTVError("All known game types attempted. Unable to play game")

            # use a lower game type. From what I can tell 2 means regular
            # season and 1 means pre-season -- pointless IMO
            try:
                archived_game = self.getArchivedGame(game_id, type-1)
            except LeafsTVError, ltvError:
                raise ltvError
            
            # return the archived game if it works as another game type
            return archived_game

        # if we get a match, make sure there is actual data
        try:
            url = match.group(1)
        except IndexError:
            raise LeafsTVError("ERROR: Unable to get URL from archived game")

        # for whatever reason the url is modified in this way for the next request        
        try:
            encrypted_game = self.getEncryptedArchivePath(re.sub('\.mp4', '_hd.mp4', url))
        except LeafsTVError, ltvErr:
            raise ltvErr
        
        # return the encrypted game URL
        return encrypted_game


    def getEncryptedArchivePath(self, path):
        """
        Get the authenticated stream url
        """
        
        # setup the request values
        values = {'isFlex' : "true",
                  'path' : path,
                  'type' : "fvod"}

        # setup the request
        req = urllib2.Request("http://leafstv.neulion.com/leafstv/servlets/encryptvideopath")
        req.add_header('cookie', self.cookie)
        req.add_data(urllib.urlencode(values))

        # make the request
        try:
            resp = urllib2.urlopen(req)
        except urllib2.URLError, ue:
            raise LeafsTVError("URL error trying to open encrypted archive: " + ue.read())
        except urllib2.HTTPError, he:
            raise LeafsTVError("HTTP error trying to open encrypted archive: " + he.read())

        # try to match the path from the response
        match = re.search('<path><\!\[CDATA\[(.*?)\]\]></path>', resp.read())
        if match == None:
            raise LeafsTVError("Unable to match archive game with <path/>")

        # ensure a valid path was returned
        try:
            url = match.group(1)
        except IndexError, ie:
            raise LeafsTVError("ERROR: Unable to get URL from archived game")

        return url