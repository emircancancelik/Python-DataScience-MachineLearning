import pytube

url = input("enter video url: ")

#pytube.YouTube(url).streams.get_highest_resolution().download()
#pytube.YouTube(url).streams.get_audio_only()
path = input("enter video path: ")
pytube.YouTube(url).streams.get_highest_resolution().download(path)