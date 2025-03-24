extern "C" {
#include <libavformat/avformat.h>
}
#include <Python.h>


static PyObject* dump_container_data(PyObject* self, PyObject* input_file) {
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

    // Iterate over each stream and add details.
    for (unsigned int i = 0; i < fmt_ctx->nb_streams; i++) {
        AVStream *stream = fmt_ctx->streams[i];
        AVCodecParameters *codecpar = stream->codecpar;
        // Initialize dict for stream
        PyObject* stream_dict = PyDict_New();
        if (!stream_dict) {
            PyErr_SetString(PyExc_RuntimeError, "Issue creating new dict for a stream");
            Py_DECREF(result);
            Py_DECREF(streams_list);
            return NULL;
        }

        // Add stream details to dict
        
        // A couple template methods
        auto add_int_to_dict = [&](const char* key, auto value) {
            PyObject* val = PyLong_FromLong(value);
            if (!val) {
                PyErr_SetString(PyExc_RuntimeError, "Issue creating new python long");
                Py_DECREF(result);
                Py_DECREF(stream_dict);
                Py_DECREF(streams_list);
                return false;
            }
            PyDict_SetItemString(stream_dict, key, val);
            Py_DECREF(val);
            return true;
        };

        auto add_str_to_dict = [&](const char* key, const char* value) {
            PyObject* val = PyUnicode_FromString(value);
            if (!val) {
                PyErr_SetString(PyExc_RuntimeError, "Issue creating new python string");
                Py_DECREF(result);
                Py_DECREF(stream_dict);
                Py_DECREF(streams_list);
                return false;
            }
            PyDict_SetItemString(stream_dict, key, val);
            Py_DECREF(val);
            return true;
        };

        if (!add_int_to_dict("index", i)) {
            return NULL;
        }

        if (!add_str_to_dict("type", av_get_media_type_string(codecpar->codec_type))) {
            return NULL;
        }
        if (!add_str_to_dict("codec", avcodec_get_name(codecpar->codec_id))) {
            return NULL;
        }
        if (codecpar->codec_type == AVMEDIA_TYPE_VIDEO) {
            if (!add_int_to_dict("bit_rate", codecpar->bit_rate)) {
                return NULL;
            }
            if (!add_int_to_dict("profile", codecpar->profile)) {
                return NULL;
            }
            if (!add_int_to_dict("level", codecpar->level)) {
                return NULL;
            }
            if (!add_int_to_dict("width", codecpar->width)) {
                return NULL;
            }
            if (!add_int_to_dict("height", codecpar->height)) {
                return NULL;
            }
        } else if (codecpar->codec_type == AVMEDIA_TYPE_AUDIO) {
            if (!add_int_to_dict("bit_rate", codecpar->bit_rate)) {
                return NULL;
            }
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

    return result;
}

// Define the module's method table.
static PyMethodDef av_info_methods[] = {
    {"dump_container_data", dump_container_data, METH_O, "Return a dictionary with a streams list."},
    {NULL, NULL, 0, NULL}
};

// Define the module.
static struct PyModuleDef av_info_module = {
    PyModuleDef_HEAD_INIT,
    "av_info",                   // Module name.
    "Module that dumps av container data", // Module documentation.
    -1,                           // Size of per-interpreter state of the module.
    av_info_methods
};


extern "C" {

// Module initialization function.
PyMODINIT_FUNC PyInit_av_info(void) {
    return PyModule_Create(&av_info_module);
}

}
