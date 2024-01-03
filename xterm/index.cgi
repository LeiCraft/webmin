#!/usr/local/bin/perl
# Show a terminal that is connected to a Websockets server via Webmin proxying
require './xterm-lib.pl';
&ReadParse();

# Check for needed modules
my @modnames = ("Digest::SHA", "Digest::MD5", "IO::Pty",
                "IO::Select", "Time::HiRes",
                "Net::WebSocket::Server");
foreach my $modname (@modnames) {
	eval "use ${modname};";
	if ($@) {
		&ui_print_header(undef, $text{'index_title'}, "", undef, 1, 1, 0);
		my $missinglink = &text('index_cpan', "<tt>$modname</tt>",
			    "../cpan/download.cgi?source=3&cpan=$modname&mode=2&return=/$module_name/&returndesc=".&urlize($module_info{'desc'}));
		if ($gconfig{'os_type'} eq 'redhat-linux') {
			$missinglink .= " ".
				&text('index_epel',
					'https://docs.fedoraproject.org/en-US/epel');
			}
		elsif ($gconfig{'os_type'} eq 'suse-linux') {
			$missinglink =
				&text('index_suse', "<tt>$modname</tt>",
					'https://software.opensuse.org/download/package?package=perl-IO-Tty&project=devel%3Alanguages%3Aperl');
			}
		if (&get_product_name() eq 'usermin') {
			print &text('index_missing', $modname) ."<p>\n";
			}
		else {
			print $missinglink ."<p>\n";
			}
		&ui_print_footer("/", $text{'index'});
		exit;
		}
	}

# Get Webmin current version for links serial
my $wver = &get_webmin_version();
$wver =~ s/\.//;

# Build Xterm dependency links
my $termlinks = 
	{ 'css' => ["xterm.css?$wver"],
	  'js'  => ["xterm.js?$wver",
	            "xterm-addon-attach.js?$wver",
	            "xterm-addon-fit.js?$wver",
	            "xterm-addon-canvas.js?$wver",
	            "xterm-addon-webgl.js?$wver"] };

# Pre-process options
my $conf_size_str = $config{'size'};
my $def_cols_n = 80;
my $def_rows_n = 24;
my $xmlhr = $ENV{'HTTP_X_REQUESTED_WITH'} eq "XMLHttpRequest";
my %term_opts;

# Parse module config
my ($conf_cols_n, $conf_rows_n) = ($conf_size_str =~ /([\d]+)X([\d]+)/i);
$conf_cols_n = int($conf_cols_n);
$conf_rows_n = int($conf_rows_n);

# Set columns and rows vars
my $env_cols = $conf_cols_n || $def_cols_n;
my $env_rows = $conf_rows_n || $def_rows_n;

# Set columns and rows environment vars only
# in fixed mode, and only for old themes
if ($conf_cols_n && $conf_rows_n && !$xmlhr) {
	$ENV{'COLUMNS'} = $conf_cols_n;
	$ENV{'LINES'} = $conf_rows_n;	
	}

# Define columns and rows
my $conf_screen_reader = $config{'screen_reader'} eq 'true' ? 'true' : 'false';
$termjs_opts{'Options'} = "{ cols: $env_cols, rows: $env_rows, screenReaderMode: $conf_screen_reader }";

my $term_size = "
	min-width: ".($conf_cols_n ? "".($conf_cols_n * 9)."px" : "calc(100vw - 22px)").";
	max-width: ".($conf_cols_n ? "".($conf_cols_n * 9)."px" : "calc(100vw - 22px)").";
	min-height: ".($conf_rows_n ? "".($conf_rows_n * 18)."px" : "calc(100vh - 55px)").";
	max-height: ".($conf_rows_n ? "".($conf_rows_n * 18)."px" : "calc(100vh - 55px)").";";

# Tweak old themes inline
my $styles_inline = <<EOF;

body[style='height:100%'] {
	height: 97% !important; 
}
#headln2l a {
	white-space: nowrap;
}
#terminal {
	border: 1px solid #000;
	background-color: #000;
	padding: 2px;
	margin: 0 auto;
	$term_size
}
#terminal:empty:before {
    display: block;
    content: " ";
    overflow: hidden;
    
    width: 12px;
    height: 12px;
    
    margin-top: 4px;
    margin-left: 4px;
    
    border-radius: 50%;
    
    box-sizing: border-box;

    border: 1px solid transparent;
    border-top-color: rgba(255, 255, 255, 0.8);
    border-bottom-color: rgba(255, 255, 255, 0.8);
    animation: jumping-spinner 1s ease infinite;
}

#terminal:empty:after {

    display: block;
    content: attr(data-label);
    margin-left: 24px;
    margin-top: -16px;
    font-weight: 100;
    color: rgba(255, 255, 255, 0.8);
    font-family: "Lucida Console", Courier, monospace;
    font-size: 14px;
    text-transform: uppercase;
}
\@keyframes jumping-spinner {
    to {
        transform: rotate(360deg);
    }
}
#terminal + script ~ * {
	display: none
}
#terminal > .terminal {
	visibility: hidden;
	animation: .15s fadeIn;
	animation-fill-mode: forwards;
}
\@keyframes fadeIn {
  99% {
    visibility: hidden;
  }
  100% {
    visibility: visible;
  }
}

EOF

# Print header
&ui_print_header(undef, $text{'index_title'}, "", undef, 1, 1, 0, undef,
		 "<link rel=stylesheet href=\"$termlinks->{'css'}[0]\">\n".
		 "<script src=\"$termlinks->{'js'}[0]\"></script>\n".
		 "<script src=\"$termlinks->{'js'}[1]\"></script>\n".
		 "<script src=\"$termlinks->{'js'}[2]\"></script>\n".
		 "<style>$styles_inline</style>\n"
		);

# Print main container
print "<div data-label=\"$text{'index_connecting'}\" id=\"terminal\"></div>\n";

# Get a free port that can be used for the socket
my $port = &allocate_miniserv_websocket();

# Check permissions for user to run as
my $user = $access{'user'};
if ($user eq "*") {
	$user = $remote_user;
	}

# Switch to given user
if ($user eq "root" && $in{'user'}) {
	defined(getpwnam($in{'user'})) ||
		&error(&text('index_euser', &html_escape($in{'user'})));
	$user = $in{'user'};
	}
my @uinfo = getpwnam($user);
@uinfo || &error(&text('index_euser', &html_escape($user)));

# Check for directory to start the shell in
my $dir = $in{'dir'};

# Launch the shell server on the allocated port
my $shellserver_cmd = "$module_config_directory/shellserver.pl";
if (!-r $shellserver_cmd) {
	&create_wrapper($shellserver_cmd, $module_name, "shellserver.pl");
	}
my $tmpdir = &tempname_dir();
$ENV{'SESSION_ID'} = $main::session_id;
&system_logged($shellserver_cmd." ".quotemeta($port)." ".quotemeta($user).
	       ($dir ? " ".quotemeta($dir) : "").
	       " >$tmpdir/ws-$port.out 2>&1 </dev/null");

# Open the terminal
my $ws_proto = lc($ENV{'HTTPS'}) eq 'on' ? 'wss' : 'ws';
my $http_host_conf = &trim($config{'host'});
if ($http_host_conf) {
		if ($http_host_conf !~ /^wss?:\/\//) {
			$http_host_conf = "$ws_proto://$http_host_conf";
			}
		$http_host_conf =~ s/[\/]+$//g;
		}

# Get the hostname from the HTTP_REFERER
my $referer_host;
if ($ENV{'HTTP_REFERER'} =~ m|^https?://([^:/]+)(?::\d+)?/|i) {
    $referer_host = $1;
}

# Check if the referer hostname is equal to ENV(HTTP_HOST)
if ($referer_host && $referer_host eq $ENV{'HTTP_HOST'}) {
    $http_real_host = "$ws_proto://$ENV{'HTTP_HOST'}";
} elsif ($referer_host && $referer_host =~ m|^(.*):10000$|) {
    $http_real_host = "$ws_proto://$ENV{'HTTP_HOST'}";
} elsif ($referer_host) {
    $http_real_host = "$ws_proto://$referer_host:10000";
}

# Define http_host variable
my $http_host = $http_host_conf || $http_real_host;

#my $http_host = $http_host_conf || "$ws_proto://$ENV{'HTTP_HOST'}";

my $url = "$http_host/$module_name/ws-$port";
my $canvasAddon = $termlinks->{'js'}[3];
my $webGLAddon = $termlinks->{'js'}[4];
my $term_script = <<EOF;

(function() {
	const socket = new WebSocket('$url', 'binary'),
	      termcont = document.getElementById('terminal'),
	      err_conn_cannot = 'Cannot connect to the socket $url',
	      err_conn_lost = 'Connection to the socket $url lost',
	      webGLAddonLink = '$webGLAddon',
	      canvasAddonLink = '$canvasAddon',
	      detectWebGLContext = (function() {
	          const canvas = document.createElement("canvas"),
	          gl = canvas.getContext("webgl") ||
	               canvas.getContext("experimental-webgl");
	          return gl instanceof WebGLRenderingContext ? true : false;
	      })();
	socket.onopen = function() {
		const term = new Terminal($termjs_opts{'Options'}),
		      attachAddon = new AttachAddon.AttachAddon(this),
		      fitAddon = new FitAddon.FitAddon(),
		      renderScript = document.createElement('script');
	  renderScript.src = detectWebGLContext ? webGLAddonLink : canvasAddonLink;
	  renderScript.async = false;
	  document.body.appendChild(renderScript);

	  // Wait to load requested render addon
	  renderScript.addEventListener('load', function() {
	      const rendererAddon = detectWebGLContext ?
	              new WebglAddon.WebglAddon() :
	              new CanvasAddon.CanvasAddon();
	      term.loadAddon(attachAddon);
	      term.loadAddon(fitAddon);
	      term.loadAddon(rendererAddon);
	      term.open(termcont);
		  setTimeout(function() {term.focus()}, 6e2);

	      // Handle case of dropping WebGL context
	      if (typeof WebglAddon === 'object') {
	        rendererAddon.onContextLoss(function() {
	          rendererAddon.dispose();
	        });
	      }

	      // On resize event triggered by fit()
	      term.onResize(function(e) {
	          socket.send('\\\\033[8;(' + e.rows + ');(' + e.cols + ')t');
	      });

	      // Observe on terminal container change
	      new ResizeObserver(function() {
	          fitAddon.fit();
	      }).observe(termcont);
	  });
	};
	socket.onerror = function() {
		termcont.innerHTML = '<tt style="color: \#ff0000">Error: ' +
			err_conn_cannot + '</tt>';
	};
	socket.onclose = function() {
		termcont.innerHTML = '<tt style="color: \#ff0000">Error: ' +
			err_conn_lost + '</tt>';
	};
})();

EOF

# Return inline script data depending on type
print "<script>\n";
if ($xmlhr) {
	print "var xterm_argv = ".
          &convert_to_json(
            { 'conf'  => \%config,
              'files' => $termlinks,
              'socket_url' => $url,
              'port'  => $port,
              'cols'  => $env_cols,
              'rows'  => $env_rows,
              'uinfo'  => \@uinfo });
	}
else {
	print $term_script;
	}
print "</script>\n";
&ui_print_footer();
