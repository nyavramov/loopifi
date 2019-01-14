/*window.setInterval(function() {
  window.scrollTo(0,document.body.scrollHeight);
}, 1000);*/
//$(allInView);
//$(window).scroll(allInView);

$(function() {
    $(".meter > span").each(function() {
        $(this)
            .data("origWidth", $(this).width())
            .width(0)
            .animate({
                width: $(this).data("origWidth")
            }, 1200);
    });
});

function isScrolledIntoView(elem) {
    var docViewTop = $(window).scrollTop();
    var docViewBottom = docViewTop + $(window).height();

    var elemTop = $(elem).offset().top;
    var elemBottom = elemTop + $(elem).height();

    return ((elemBottom <= docViewBottom) && (elemTop >= docViewTop));
}

$(window).on("scroll", function() {
    $('video').each(function() {
        if (isScrolledIntoView(this)) {
            this.play();
        } else {
            this.pause();
        }
    });
});

function manageControls(i) {
    // Video
    console.log("lol running");

    var video = document.getElementById("video" + i);
    var playButton = document.getElementById("play-pause" + i);
    var muteButton = document.getElementById("mute" + i);
    var fullScreenButton = document.getElementById("full-screen" + i);
    var seekBar = document.getElementById("seek-bar" + i);
    var volumeBar = document.getElementById("volume-bar" + i);



    // Event listener for the play/pause button
    playButton.addEventListener("click", function() {

        console.log(this.parentNode.parentNode.childNodes[1]);
        theVideo = this.parentNode.parentNode.childNodes[1];
        if (theVideo.paused == true) {
            // Play the video
            theVideo.play();

            // Update the button text to 'Pause'
            this.innerHTML = "Pause";
        } else {
            // Pause the video
            theVideo.pause();

            // Update the button text to 'Play'
            this.innerHTML = "Play";
        }
        
    });


    // Event listener for the mute button
    muteButton.addEventListener("click", function() {
        console.log(this.parentNode.parentNode.childNodes[1]);
        theVideo = this.parentNode.parentNode.childNodes[1];
        //theMuteButton = this.parentNode.parentNode.childNodes[7].childNodes[5]
        if (theVideo.muted == false) {
            // Mute the video
            theVideo.muted = true;

            // Update the button text
            this.innerHTML = "Unmute";
        } else {
            // Unmute the video
            theVideo.muted = false;

            // Update the button text
            this.innerHTML = "Mute";
        }
    });


    // Event listener for the full-screen button
    fullScreenButton.addEventListener("click", function() {
        console.log(this.parentNode.parentNode.childNodes[1]);
        theVideo = this.parentNode.parentNode.childNodes[1];
        if (theVideo.requestFullscreen) {
            theVideo.requestFullscreen();
        } else if (theVideo.mozRequestFullScreen) {
            theVideo.mozRequestFullScreen(); // Firefox
        } else if (theVideo.webkitRequestFullscreen) {
            theVideo.webkitRequestFullscreen(); // Chrome and Safari
        }
    });


    // Event listener for the seek bar
    seekBar.addEventListener("change", function() {
        theVideo = this.parentNode.parentNode.childNodes[1];
        // Calculate the new time
        var time = theVideo.duration * (seekBar.value / 100);
        
        // Update the video time
        theVideo.currentTime = time;
    });

    
    // Update the seek bar as the video plays
    video.addEventListener("timeupdate", function() {
        console.log(this.parentNode.childNodes[2].childNodes[3]);
        console.log(this.parentNode.childNodes[1]);
        var theSeekBar = this.parentNode.childNodes[2].childNodes[3];
        var theVideo = this.parentNode.childNodes[1];
        if (isScrolledIntoView(this)){
            console.log("lol");
        }
        // Calculate the slider value
        var value = (100 / theVideo.duration) * video.currentTime;

        // Update the slider value
        theSeekBar.value = value;
    });

    // Pause the video when the seek handle is being dragged
    seekBar.addEventListener("mousedown", function() {
        theVideo = this.parentNode.parentNode.childNodes[1];
        theVideo.pause();
    });

    // Play the video when the seek handle is dropped
    seekBar.addEventListener("mouseup", function() {
        theVideo = this.parentNode.parentNode.childNodes[1];
        theVideo.play();
    });

    // Event listener for the volume bar
    volumeBar.addEventListener("change", function() {
        theVideo = this.parentNode.parentNode.childNodes[1];
        // Update the video volume
        theVideo.volume = volumeBar.value;
    });
    

    /*
    // Buttons
    var playButton = document.getElementById("play-pause");
    var muteButton = document.getElementById("mute");
    var fullScreenButton = document.getElementById("full-screen");

    // Sliders
    var seekBar = document.getElementById("seek-bar");
    var volumeBar = document.getElementById("volume-bar");


    // Event listener for the play/pause button
    playButton.addEventListener("click", function() {
        if (video.paused == true) {
            // Play the video
            video.play();

            // Update the button text to 'Pause'
            playButton.innerHTML = "Pause";
        } else {
            // Pause the video
            video.pause();

            // Update the button text to 'Play'
            playButton.innerHTML = "Play";
        }
    });


    // Event listener for the mute button
    muteButton.addEventListener("click", function() {
        if (video.muted == false) {
            // Mute the video
            video.muted = true;

            // Update the button text
            muteButton.innerHTML = "Unmute";
        } else {
            // Unmute the video
            video.muted = false;

            // Update the button text
            muteButton.innerHTML = "Mute";
        }
    });


    // Event listener for the full-screen button
    fullScreenButton.addEventListener("click", function() {
        if (video.requestFullscreen) {
            video.requestFullscreen();
        } else if (video.mozRequestFullScreen) {
            video.mozRequestFullScreen(); // Firefox
        } else if (video.webkitRequestFullscreen) {
            video.webkitRequestFullscreen(); // Chrome and Safari
        }
    });


    // Event listener for the seek bar
    seekBar.addEventListener("change", function() {
        // Calculate the new time
        var time = video.duration * (seekBar.value / 100);

        // Update the video time
        video.currentTime = time;
    });

    
    // Update the seek bar as the video plays
    video.addEventListener("timeupdate", function() {
        // Calculate the slider value
        var value = (100 / video.duration) * video.currentTime;

        // Update the slider value
        seekBar.value = value;
    });

    // Pause the video when the seek handle is being dragged
    seekBar.addEventListener("mousedown", function() {
        video.pause();
    });

    // Play the video when the seek handle is dropped
    seekBar.addEventListener("mouseup", function() {
        video.play();
    });

    // Event listener for the volume bar
    volumeBar.addEventListener("change", function() {
        // Update the video volume
        video.volume = volumeBar.value;
    });*/
}
