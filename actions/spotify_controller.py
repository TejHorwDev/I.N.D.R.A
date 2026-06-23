import subprocess
import urllib.parse
import os

def spotify_controller(parameters: dict, player=None) -> str:
    """
    Controls Spotify to play a specific song, artist, or playlist.
    """
    query = parameters.get("query", "").strip()
    if not query:
        return "No search query provided for Spotify."
        
    encoded_query = urllib.parse.quote(query)
    
    # Spotify URI format for searching
    spotify_uri = f"spotify:search:{encoded_query}"
    
    try:
        if os.name == 'nt':
            os.startfile(spotify_uri)
        else:
            subprocess.run(["open", spotify_uri] if sys.platform == "darwin" else ["xdg-open", spotify_uri])
        return f"Opened Spotify and searched for: {query}"
    except Exception as e:
        return f"Failed to open Spotify: {e}"
