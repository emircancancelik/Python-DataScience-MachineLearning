import spotipy
from spotipy.oauth2 import SpotifyOAuth
import pandas as pd

# informations
client_id = 'account key'
client_secret = 'Secret key'
redirect_uri = 'Site link' 
playlist_id = 'List ID' # Global Top 50 Listesi

# spotify connection
auth_manager = SpotifyOAuth(client_id=client_id,
                            client_secret=client_secret,
                            redirect_uri=redirect_uri,
                            scope="playlist-read-private playlist-read-collaborative",
                            open_browser=False)
sp = spotipy.Spotify(auth_manager=auth_manager)

# 3. data pull
results = sp.playlist_items(playlist_id)
tracks = results['items']

data = []
for item in tracks:
    track = item['track']
    if track:
        data.append({
            'id': track['id'],
            'name': track['name'],
            'artist': track['artists'][0]['name'],
            'added_by': item['added_by']['id']
        })

df = pd.DataFrame(data)

# technical information
track_ids = df['id'].tolist()
audio_features = sp.audio_features(track_ids)
features_df = pd.DataFrame(audio_features)

final_df = pd.merge(df, features_df[['id', 'danceability', 'energy', 'valence', 'tempo']], on='id')

print("Veriler başarıyla çekildi!")
print(final_df.head())