#
# This file is part of the RapidMiner Python package.
#
# Copyright (C) 2018-2019 RapidMiner GmbH
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU Affero General Public License as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.
# If not, see https://www.gnu.org/licenses/.
#
import pandas
import json
import sys
import numpy as np
import base64
import datetime

try:
    from .. import __version__
except:
    __version__ = "0.0.0" # replaced by extension code

# instance(x, basestring) works with Python 2 and 3 this way
try:
    basestring
except NameError:
    basestring = str

class DateConversionError(ValueError):
    def __init__(self, msg):
        super(DateConversionError, self).__init__(msg)

def __open_file_python2(file, mode):
    return open(file, mode)

def __open_file_python3(file, mode):
    return open(file, mode, encoding="utf-8")

def __write_file_python2(file, object):
    if type(object) != unicode:
        if type(object) != str:
            object = str(object)
        object = unicode(object, "utf-8")
    file.write(object.encode("utf-8"))

def __write_file_python3(file, object):
    file.write(str(object))

def read_file(file):
    return file.read()

def __b64encode_python2(str):
    return base64.b64encode(str)

def __b64encode_python3(str):
    return base64.b64encode(str.encode("utf-8")).decode("utf-8")

def __b64decode_python2(str):
    return base64.b64decode(str)

def __b64decode_python3(str):
    return base64.b64decode(str.encode("utf-8")).decode("utf-8")

if sys.version_info >= (3, 0):
    open_file = __open_file_python3
    write_file = __write_file_python3
    b64encode = __b64encode_python3
    b64decode = __b64decode_python3
else:
    open_file = __open_file_python2
    write_file = __write_file_python2
    b64encode = __b64encode_python2
    b64decode = __b64decode_python2

# writes string to error file
def write_to_error_log(full_message):
    with open_file("rapidminer_error.log", "w") as error_file:
        write_file(error_file, full_message)

# transforms meta data list to a dictionary
def transform_metadata(list):
    dict = {}
    for element in list:
        name, (type, role) = next(iter(element.items()))
        name = __handle_unicode(name)
        type = __handle_unicode(type)
        role = __handle_unicode(role)

        # "attribute" role is handled differently due to backward compatibility
        if role == "attribute":
            dict[name] = (type, None)
        else:
            dict[name] = (type, role)
    return dict

# reads the example set from the files into a pandas.DataFrame.
def read_example_set(input_csv, input_pmd):
    def read_date(epoch):
        if epoch != "null" and epoch is not pandas.np.nan and epoch == epoch:
            # because of some older pandas versions, we need to read in "ns"
            return pandas.to_datetime(int(epoch)*1000, unit='ns')
        else:
            return None

    # metadata
    metadata = json.loads(read_file(input_pmd))["metadata"]
    dtype = {}
    rename_map = {}
    conv = {}
    date_cols = []
    index = 0
    for attr_info in metadata:
        attr, (rm_type, _) = next(iter(attr_info.items()))
        attr = __handle_unicode(attr)
        rm_type = __handle_unicode(rm_type)
        if rm_type in ["real", "numeric"]:
            dtype[index] = "float64"
        elif __nominal_meta_type(rm_type):
            conv[index] = lambda x: b64decode(x) if x != "null" else np.nan
        elif __date_meta_type(rm_type):
            # "datetime64[ms]" is not allowed
            dtype[index] = "object"
            date_cols.append(index)
        elif rm_type != "integer":
            # "int64" may fail because of missings, not setting type in this case: it will either be float64 (missings) or int64
            print("type in '" + rm_type + "' is not a valid rapidminer type")
            write_to_error_log("type in '" + rm_type + "' is not a valid rapidminer type")
            sys.exit(65)
        rename_map[index] = attr
        index = index + 1
    # data
    df = pandas.read_csv(input_csv,
                         dtype=dtype,
                         encoding="utf-8",
                         header=None,
                         converters=conv,
                         parse_dates=date_cols,
                         date_parser=lambda epoch: read_date(epoch))
    df.rename(columns=rename_map, inplace=True)
    set_metadata_without_warning(df, transform_metadata(metadata))
    return df

# uses the meta data from rm_metadata attribute if present
# otherwise deduces the type from the data and sets no special role
def get_metadata(data, original_names):
    metadata = []

    #check if rm_metadata attribute is present and a dictionary
    try:
        if hasattr(data, "rm_metadata") and isinstance(data.rm_metadata,dict):
            meta_isdict = True
        elif hasattr(data, "rm_metadata"):
            meta_isdict = False
            if data.rm_metadata is not None:
                print("Warning: rm_metadata must be a dictionary")
        else:
            meta_isdict = False
    except:
        meta_isdict = False

    for name in data.columns.values:
        try:
            original_name = original_names[name] if name in original_names else name
            if hasattr(data, "rm_metadata"):
                meta = data.rm_metadata[original_name]
            else:
                meta = None
            #take entries only if tuple of length 2
            if isinstance(meta,tuple) and len(meta)==2 and meta_isdict:
                meta_type, meta_role = meta
            else:
                if meta_isdict and meta is not None:
                    print("Warning: rm_metadata["+str(original_name)+"] must be a tuple of length 2, e.g. data.rm_metadata['column1']=('binominal','label')")
                # if the format of metadata is not correct, still try to figure out meta type and role
                if isinstance(meta, basestring) and len(meta) > 0:
                    meta_type = meta
                    meta_role = None
                elif (isinstance(meta, tuple) or isinstance(meta, list)) and len(meta) > 0:
                    meta_type = meta[0]
                    if len(meta) > 1:
                        meta_role = meta[1]
                    else:
                        meta_role = None
                else:
                    meta_type = None
                    meta_role = None
            meta_type = __handle_unicode(meta_type)
            meta_role = __handle_unicode(meta_role)
        except Exception as e:
            print(e)
            meta_type = None
            meta_role = None

        if meta_role is None:
            meta_role = 'attribute'
        #choose type by dtype of the column
        if meta_type is None or not __valid_meta_type(meta_type):
            kind_char = data.dtypes[name].kind
            if kind_char in ('i','u'):
                meta_type = 'integer'
            elif kind_char in ('f'):
                meta_type = 'real'
            elif kind_char in ('M'):
                meta_type = 'date_time'
            elif kind_char in ('b'):
                meta_type = 'binominal'
            else:
                meta_type = 'polynominal'
        # double quote and backslash characters are escaped automatically in the name key
        metadata.append({name : (meta_type,meta_role)})
    return metadata

# if name has a string representation containing non-ascii symbols in python 2,
# for example if name is a python 2 unicode with umlauts, then str(name) results in exception;
# in this case it is in particular not empty and contains more than only digits
def isstringable(name):
    try:
        str(name)
        return True
    except:
        return False

def is_invalid_name(name):
    return isstringable(name) and ((not str(name)) or str(name).isdigit())

def rename_columns(dataframe):
    original_names = {}
    # column name must not be empty or a number
    if any(is_invalid_name(name) for name in dataframe.columns.values):
        new_columns = []
        for name in dataframe.columns.values:
            new_name = name
            if is_invalid_name(name):
                new_name = 'att'+str(name)
                original_names[new_name] = name
            new_columns.append(new_name)
        dataframe.columns = new_columns
    return original_names

# base64 encode all nominals and convert dates to epoch
__converted_dataframes__=[]
def convert_to_output_format(df, metadata):
    def b64(x):
        if pandas.isnull(x):
            return "null"
        elif isinstance(x, basestring) and len(x) > 0:
            return b64encode(x)
        return b64encode(str(x))

    if (id(df) in __converted_dataframes__):
        return

    for m in metadata:
        # there is just one column in one list element
        for name in m:
            meta_type = m[name][0]
            if __date_meta_type(meta_type):
                index = pandas.np.logical_not(df[name].isnull())
                if not any(index):
                    # we have only null values
                    continue
                try:
                    if all(index):
                        # // operator is necessary to keep type int in all python, pandas versions
                        df[name] = df[name].astype("int64")//1000
                    else:
                        # workaround for pandas error in some older pandas version
                        if type(index) == pandas.Series:
                            try:
                                # this will always raise errors with older pandas versions
                                index[0:0].dropna()
                            except TypeError:
                                index = index.tolist()
                        df.loc[index, name] = df.loc[index,name].astype("int64")
                        # check if conversion succeeded (for pandas==0.17.1 for example it is not working)
                        sample = df.loc[index, name].iloc[0]
                        if __is_integer_number(sample):
                            # // operator is necessary to keep type int in all python, pandas versions
                            df.loc[index, name] = df.loc[index,name]//1000
                        else:
                            df[name] = df[name].astype("object")
                            df.loc[index, name] = ((df.loc[index, name] - pandas.to_datetime(0, unit="ns")).dt.total_seconds()*1e6).round().astype("int64")
                except ValueError:
                    raise DateConversionError("Error while serializing dataframe: some values in column '" + str(name) + "' are not valid dates.")
            elif __nominal_meta_type(meta_type):
                df[name] = df[name].apply(b64)
    __converted_dataframes__.append(id(df))

# writes the data and metadata to files
# SIDE EFFECT: the method may modify the original data
def write_example_set(data, output_csv, output_pmd):
    original_names = rename_columns(data)
    # metadata
    metadata = get_metadata(data, original_names)
    write_file(output_pmd, "{\n")
    write_file(output_pmd, "  \"source\": \"RapidMiner Python Scripting Extension and Library\",\n")
    write_file(output_pmd, "  \"module\": \"Python\",\n")
    write_file(output_pmd, "  \"version\": \"" + __version__ + "\",\n")
    write_file(output_pmd, "  \"metadata\":\n" + json.dumps(metadata))
    write_file(output_pmd, "\n}")
    # data
    convert_to_output_format(data, metadata)
    data.to_csv(output_csv, encoding="utf-8", header=False, index=False)

def set_metadata_without_warning(df, metadata):
    try:
        import warnings
    except:
        df.rm_metadata = metadata
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df.rm_metadata = metadata

# based on Ontology
def __valid_meta_type(meta_type):
    return meta_type in [None, "integer", "real", "numeric"] or __nominal_meta_type(meta_type) or __date_meta_type(meta_type)

def __nominal_meta_type(meta_type):
    return meta_type in ["nominal", "binominal", "polynominal", "text", "file_path"]

def __date_meta_type(meta_type):
    return meta_type in ["date_time", "date", "time"]

# ensures python2 compatibility
def __handle_unicode(value):
    if sys.version_info.major == 2:
        if type(value) == unicode:
            return value.encode("utf-8")
    return value

def __is_integer_number(vut):
    try:
        vut + 1
        return True
    except:
        return False