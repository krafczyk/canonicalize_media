extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/avutil.h>
#include <libavutil/dict.h> // for av_dict_get
}
#include <Python.h>


static PyObject* ffmpeg(PyObject* self, PyObject* input_file) {
    // Check that the input file is a string.
    if (!PyUnicode_Check(input_file)) {
      PyErr_SetString(PyExc_TypeError, "Input file must be a string.");
      return NULL;
    }

    // Convert the input file to a C string.
    const char* input_file_str = PyUnicode_AsUTF8(input_file);

    AVFormatContext *fmt_ctx = NULL;

    // Open the input file
    if (avformat_open_input(&fmt_ctx, input_file_str, NULL, NULL) < 0) {
        char buffer[1024];
        snprintf(buffer, sizeof(buffer), "Could not open input file '%s'\n", input_file_str);
        PyErr_SetString(PyExc_RuntimeError, buffer);
        return NULL;
    }

    // Retrieve stream information
    if (avformat_find_stream_info(fmt_ctx, NULL) < 0) {
        char buffer[1024];
        snprintf(buffer, sizeof(buffer), "Could not find stream information '%s'\n", input_file_str);
        PyErr_SetString(PyExc_RuntimeError, buffer);
        avformat_close_input(&fmt_ctx);
        return NULL;
    }

    // Initialize Python dict
    PyObject* result = PyDict_New();
    if (!result) {
        PyErr_SetString(PyExc_RuntimeError, "Issue creating new dict");
        return NULL;
    }

    // Initialize the streams list
    PyObject *streams_list = PyList_New(0);
    if (!streams_list) {
        PyErr_SetString(PyExc_RuntimeError, "Issue creating new list");
        Py_DECREF(result);
        return NULL;
    }

    // Helper methods
    auto add_int_to_dict = [&](auto dict, const char* key, auto value) {
        PyObject* val = PyLong_FromLong(value);
        if (!val) {
            PyErr_SetString(PyExc_RuntimeError, "Issue creating new python long");
            return false;
        }
        PyDict_SetItemString(dict, key, val);
        Py_DECREF(val);
        return true;
    };

    auto add_str_to_dict = [&](auto dict, const char* key, const char* value) {
        PyObject* val = PyUnicode_FromString(value);
        if (!val) {
            PyErr_SetString(PyExc_RuntimeError, "Issue creating new python string");
            return false;
        }
        PyDict_SetItemString(dict, key, val);
        Py_DECREF(val);
        return true;
    };

    auto add_double_to_dict = [&](PyObject* dict, const char* key, double val) {
        PyObject* pyf = PyFloat_FromDouble(val);
        if (!pyf) {
            PyErr_SetString(PyExc_RuntimeError, "Could not create float");
            return false;
        }
        PyDict_SetItemString(dict, key, pyf);
        Py_DECREF(pyf);
        return true;
    };

    // Iterate over each stream and add details.
    for (unsigned int i = 0; i < fmt_ctx->nb_streams; i++) {
        AVStream *stream = fmt_ctx->streams[i];
        AVCodecParameters *codecpar = stream->codecpar;
        PyObject* stream_dict = PyDict_New();

        if (!stream_dict) {
            PyErr_SetString(PyExc_RuntimeError, "Issue creating new dict for a stream");
            Py_DECREF(result);
            Py_DECREF(streams_list);
            return NULL;
        }

        // Add stream details to dict
        auto cleanup = [&]() {
            Py_DECREF(result);
            Py_DECREF(stream_dict);
            Py_DECREF(streams_list);
            return (PyObject*) NULL;
        };
        
        // Common fields
        if (!add_int_to_dict(stream_dict, "index", i)) return cleanup();
        if (!add_str_to_dict(stream_dict, "type", av_get_media_type_string(codecpar->codec_type))) return cleanup();
        if (!add_str_to_dict(stream_dict, "codec", avcodec_get_name(codecpar->codec_id))) return cleanup();

        if (codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            int64_t bit_rate = codecpar->bit_rate;
            if (bit_rate == 0) {
                // Calculate bitrate from frame size and duration
                if (stream->duration > 0) {
                    int64_t file_size = fmt_ctx->pb ? avio_size(fmt_ctx->pb) : 0;
                    if (file_size > 0) {
                        // duration is in AV_TIME_BASE (microseconds); convert to seconds
                        double duration_sec = stream->duration * av_q2d(stream->time_base);
                        bit_rate = (int64_t)((file_size * 8) / duration_sec);
                    }
                }
            }
            if (!add_int_to_dict(stream_dict, "bit_rate", bit_rate)) return cleanup();
            if (!add_int_to_dict(stream_dict, "profile", codecpar->profile)) return cleanup();
            if (!add_str_to_dict(stream_dict, "profile_name", avcodec_profile_name(codecpar->codec_id, codecpar->profile))) {
                return cleanup();
            }
            if (!add_int_to_dict(stream_dict, "level", codecpar->level)) return cleanup();
            if (!add_int_to_dict(stream_dict, "width", codecpar->width)) return cleanup();
            if (!add_int_to_dict(stream_dict, "height", codecpar->height)) return cleanup();
        } else if (codecpar->codec_type == AVMEDIA_TYPE_AUDIO) {
            if (!add_int_to_dict(stream_dict, "bit_rate", codecpar->bit_rate)) return cleanup();
        } else if (codecpar->codec_type == AVMEDIA_TYPE_SUBTITLE) {
            // pull out language tag (e.g. "eng", "fra"), default to "und"
            AVDictionaryEntry *lang_tag = av_dict_get(stream->metadata, "language", NULL, 0);
            const char* lang = lang_tag ? lang_tag->value : "und";
            if (!add_str_to_dict(stream_dict, "language", lang)) return cleanup();

            // title
            AVDictionaryEntry *ttl = av_dict_get(stream->metadata, "title", nullptr, 0);
            const char *title = ttl ? ttl->value : "";
            if (!add_str_to_dict(stream_dict, "title", title)) return cleanup();

            const char *codec_name  = avcodec_get_name(codecpar->codec_id);          // "ass", "webvtt", "hdmv_pgs_subtitle", …
            const AVCodecDescriptor *desc = avcodec_descriptor_get(codecpar->codec_id);
            const char *codec_long = desc ? desc->long_name : codec_name;            // "SSA/ASS subtitle", …
            if (!add_str_to_dict(stream_dict, "codec",      codec_name))  return cleanup();
            if (!add_str_to_dict(stream_dict, "codec_long", codec_long)) return cleanup();

            // format (FourCC from codec_tag)
            char tagbuf[AV_FOURCC_MAX_STRING_SIZE];
            av_fourcc_make_string(tagbuf, codecpar->codec_tag);
            // tagbuf now holds the four-character code + '\0'
            if (!add_str_to_dict(stream_dict, "format", tagbuf)) return cleanup();
        }

        if (PyList_Append(streams_list, stream_dict) == -1) {
            PyErr_SetString(PyExc_RuntimeError, "Issue appending");
            Py_DECREF(result);
            Py_DECREF(stream_dict);
            Py_DECREF(streams_list);
            return NULL;
        }
        Py_DECREF(stream_dict);
    }

    // Add streams list to result
    PyDict_SetItemString(result, "streams", streams_list);
    Py_DECREF(streams_list);

    if (fmt_ctx->nb_chapters > 0) {
        PyObject* chapters_list = PyList_New(0);
        if (!chapters_list) {
            PyErr_SetString(PyExc_RuntimeError, "Could not create chapters list");
            Py_DECREF(result);
            return NULL;
        }

        for (unsigned int j = 0; j < fmt_ctx->nb_chapters; j++) {
            AVChapter* chapter = fmt_ctx->chapters[j];
            PyObject* chap_dict = PyDict_New();
            if (!chap_dict) {
                PyErr_SetString(PyExc_RuntimeError, "Could not create chapter dict");
                Py_DECREF(chapters_list);
                Py_DECREF(result);
                return NULL;
            }

            // chapter id
            if (!add_int_to_dict(chap_dict, "id", chapter->id)) {
                Py_DECREF(chap_dict);
                Py_DECREF(chapters_list);
                return NULL;
            }

            // start / end (in seconds)
            double start_sec = chapter->start * av_q2d(chapter->time_base);
            double end_sec   = chapter->end   * av_q2d(chapter->time_base);
            if (!add_double_to_dict(chap_dict, "start_time", start_sec) ||
                !add_double_to_dict(chap_dict, "end_time",   end_sec))
            {
                Py_DECREF(chap_dict);
                Py_DECREF(chapters_list);
                return NULL;
            }

            // optional title
            AVDictionaryEntry* e = av_dict_get(chapter->metadata, "title", NULL, 0);
            const char* title = e ? e->value : "";
            if (!add_str_to_dict(chap_dict, "title", title)) {
                Py_DECREF(chap_dict);
                Py_DECREF(chapters_list);
                return NULL;
            }

            if (PyList_Append(chapters_list, chap_dict) < 0) {
                PyErr_SetString(PyExc_RuntimeError, "Could not append chapter");
                Py_DECREF(chap_dict);
                Py_DECREF(chapters_list);
                Py_DECREF(result);
                return NULL;
            }
            Py_DECREF(chap_dict);
        }

        // attach to top-level result dict
        if (PyDict_SetItemString(result, "chapters", chapters_list) < 0) {
            PyErr_SetString(PyExc_RuntimeError, "Could not set chapters key");
            Py_DECREF(chapters_list);
            Py_DECREF(result);
            return NULL;
        }
        Py_DECREF(chapters_list);
    }

    return result;
}

// Define the module's method table.
static PyMethodDef ffmpeg_methods[] = {
    {"ffmpeg", ffmpeg, METH_O, "Return a dictionary with container information produced by ffmpeg"},
    {NULL, NULL, 0, NULL}
};

// Define the module.
static struct PyModuleDef ffmpeg_module = {
    PyModuleDef_HEAD_INIT,
    "_ffmpeg",                   // Module name.
    "Module that dumps av container data using ffmpeg", // Module documentation.
    -1,                           // Size of per-interpreter state of the module.
    ffmpeg_methods
};


extern "C" {

// Module initialization function.
PyMODINIT_FUNC PyInit__ffmpeg(void) {
    return PyModule_Create(&ffmpeg_module);
}

}
